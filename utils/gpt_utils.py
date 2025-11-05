import os
import json
import re
from typing import List, Dict, Any, Tuple

from openai import OpenAI

LM_BASE_URL = os.getenv("LM_BASE_URL", "http://127.0.0.1:80/v1")
LM_MODEL_ID = os.getenv("LM_MODEL_ID", "meta-llama-3.1-8b-instruct-128k")
LM_API_KEY   = os.getenv("OPENAI_API_KEY", "lm-studio")

client = OpenAI(base_url=LM_BASE_URL, api_key=LM_API_KEY)

# ---------- helpers ----------
def _extract_json_block(text: str) -> str:
    if not text:
        raise ValueError("Empty text")
    m = re.search(r"```json\s*({[\s\S]*?})\s*```", text, re.IGNORECASE)
    if m: return m.group(1).strip()
    m = re.search(r"```\s*({[\s\S]*?})\s*```", text, re.IGNORECASE)
    if m: return m.group(1).strip()
    s = text.find("{"); e = text.rfind("}")
    if s != -1 and e != -1 and e > s:
        return text[s:e+1].strip()
    raise ValueError("No JSON object found")

def _json_loads_safe(s: str) -> Dict[str, Any]:
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        s2 = s.replace("“", '"').replace("”", '"').replace("’", "'")
        return json.loads(s2)

def _normalize(s: str) -> str:
    return (s or "").strip().lower()

def _tokenize(s: str) -> List[str]:
    s = (s or "").lower()
    s = re.sub(r"[ăâîșşţț]", lambda m: {
        "ă":"a","â":"a","î":"i","ș":"s","ş":"s","ţ":"t","ț":"t"
    }[m.group(0)], s)
    return [w for w in re.findall(r"[a-z0-9]+", s) if len(w) > 2]

# ---------- KPI mapping (existing) ----------
def _score_kpi(candidate: str, reference: str) -> float:
    c = _normalize(candidate); r = _normalize(reference)
    score = 0.0
    if c == r: score += 1000.0
    if r in c or c in r: score += 200.0 + min(len(c), len(r)) * 0.5
    ct = set(_tokenize(c)); rt = set(_tokenize(r))
    inter = len(ct & rt); uni = max(1, len(ct | rt))
    score += (inter/uni) * 100.0
    score += len(reference) / 100.0
    return score

def _map_to_exact_kpis(candidates: List[str], all_kpis: List[str]) -> Tuple[List[str], Dict[str, str]]:
    exacts, trace, seen = [], {}, set()
    for cand in candidates:
        if not cand: continue
        best, best_score = None, -1.0
        for k in all_kpis:
            sc = _score_kpi(str(cand), str(k))
            if sc > best_score: best_score, best = sc, k
        if best and best not in seen:
            seen.add(best); exacts.append(best)
            if _normalize(best) != _normalize(cand):
                trace[best] = cand
    return exacts, trace

# ---------- public API ----------
def match_kpis_with_ai(title: str, topic: str, agenda: List[Dict[str, str]], kpis: List[str]) -> Dict[str, Any]:
    title = title or ""; topic = topic or ""
    agenda_titles = [a.get("title","") for a in (agenda or []) if a]
    kpis = [str(x).strip() for x in (kpis or []) if str(x).strip()]
    agenda_block = "\n".join(f"- {t}" for t in agenda_titles) or "–"
    kpi_block = "\n".join(f"- {k}" for k in kpis) or "–"

    system_rules = (
        "You are a meticulous assistant that aligns meeting content with a predefined KPI list. "
        "You MUST ONLY select KPIs from the provided list, using the exact, full string as written. "
        "Do not shorten, paraphrase, or invent KPIs. Do not add new KPIs. "
        "Evaluate EACH KPI independently against the meeting signals. "
        "There is NO maximum; include ALL KPIs that clearly apply."
    )

    prompt = f"""Analyze the meeting and decide which KPIs from the provided list are addressed. 
Your task is recall-oriented: select ALL that apply.

Meeting Title: {title}
Theme: {topic}

Agenda:
{agenda_block}

KPI CANDIDATES (the ONLY allowed options):
{kpi_block}

INSTRUCTIONS:
- Use the EXACT KPI text as written above. Do NOT abbreviate or invent.
- For each matched KPI, provide a brief explanation (1–2 sentences) referencing specific cues (title/topic/agenda).
- Return unmatched KPIs as the remainder (all candidates minus matched_kpis).
- Output STRICT JSON ONLY:

{{
  "matched_kpis": [
    {{
      "kpi": "<EXACT KPI TEXT>",
      "why": "<short explanation referencing title/topic/agenda>",
      "confidence": 0-100
    }}
  ],
  "unmatched_kpis": ["<EXACT KPI TEXT>", "..."]
}}
"""

    try:
        resp = client.chat.completions.create(
            model=LM_MODEL_ID,
            messages=[{"role":"system","content":system_rules},{"role":"user","content":prompt}],
            temperature=0.2,
        )
        raw = resp.choices[0].message.content.strip()
        json_str = _extract_json_block(raw)
        data = _json_loads_safe(json_str)

        llm_matched = []
        if isinstance(data.get("matched_kpis"), list):
            for item in data["matched_kpis"]:
                if isinstance(item, dict): llm_matched.append(item.get("kpi",""))
                else: llm_matched.append(str(item))

        exact_matched, trace = _map_to_exact_kpis(llm_matched, kpis)

        details = []
        if isinstance(data.get("matched_kpis"), list):
            for item in data["matched_kpis"]:
                if isinstance(item, dict):
                    exact, _ = _map_to_exact_kpis([item.get("kpi","")], kpis)
                    if exact:
                        det = {"kpi": exact[0], "why": (item.get("why","") or "").strip()}
                        conf = item.get("confidence", None)
                        if isinstance(conf,(int,float)): det["confidence"] = float(conf)
                        details.append(det)
                else:
                    exact,_ = _map_to_exact_kpis([str(item)], kpis)
                    if exact: details.append({"kpi": exact[0], "why": ""})

        llm_unmatched = []
        if isinstance(data.get("unmatched_kpis"), list):
            llm_unmatched = [str(x) for x in data["unmatched_kpis"]]
        exact_unmatched,_ = _map_to_exact_kpis(llm_unmatched, kpis)

        matched_set = set(exact_matched)
        all_set = set(kpis)
        rest = [k for k in kpis if k not in matched_set and k not in exact_unmatched]
        exact_unmatched = exact_unmatched + rest

        return {
            "matched_kpis": exact_matched,
            "details": details,
            "unmatched_kpis": exact_unmatched,
            "trace": trace,
            "raw_model": raw,
        }
    except Exception as e:
        return {"matched_kpis": [], "details": [], "unmatched_kpis": kpis, "error": f"AI matching failed: {e}"}

def generate_newsletter_ai(meeting_data: Dict[str, Any]) -> str:
    """(kept for compatibility) Full HTML newsletter – unchanged here."""
    title = meeting_data.get("title", "QA Meeting")
    date = meeting_data.get("date", "TBD")
    topic = meeting_data.get("topic", "")
    participants = meeting_data.get("participants", []) or []
    agenda = meeting_data.get("agenda", []) or []
    kpis = meeting_data.get("kpis", []) or []

    agenda_lines = "\n".join(
        f"{a.get('start','')}–{a.get('end','')}  {a.get('title','')}".strip() for a in agenda
    ).strip()
    kpi_lines = "\n".join(f"- {k}" for k in kpis).strip()

    prompt = f"""Create a concise internal newsletter as a clean HTML fragment (no external CSS), summarizing the QA leadership meeting.

Title: {title}
Date: {date}
Theme: {topic}

Agenda:
{agenda_lines or "–"}

KPIs addressed (verbatim list):
{kpi_lines or "–"}

REQUIREMENTS:
- Output ONLY a single valid HTML fragment (<div>…</div>).
- Do NOT include any invitations, calls-to-action, registration links, or future event logistics.
- Use short sections and bullets.
"""

    try:
        resp = client.chat.completions.create(
            model=LM_MODEL_ID,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        html = (resp.choices[0].message.content or "").strip()
        m = re.search(r"```html\s*([\s\S]+?)\s*```", html, re.IGNORECASE)
        if m: return m.group(1).strip()
        if "<div" not in html: html = f"<div>{html}</div>"
        return html
    except Exception:
        return f"<div><h3>{title} – {date}</h3><pre>{agenda_lines or '–'}</pre></div>"

def generate_newsletter_overlay(meeting_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns a strict JSON with:
      { "headline": str, "subheadline": str, "bullets": [str, ...] }

    Purpose: POST-event recap (no invitations/CTA/links). Short bullets, 4–6,
    focused on results/learning; use agenda (+ KPIs if available).
    """
    title = meeting_data.get("title", "QA Meeting")
    date  = meeting_data.get("date", "TBD")
    topic = meeting_data.get("topic", "")
    agenda = meeting_data.get("agenda", []) or []
    kpis   = meeting_data.get("kpis", []) or []

    ag_lines = "\n".join(f"- {a.get('start','')}–{a.get('end','')}: {a.get('title','')}".strip() for a in agenda) or "–"
    kpi_lines = "\n".join(f"- {k}" for k in kpis) or "–"

    system = (
        "You write post-event summaries for internal newsletters. "
        "Your style is crisp, energetic, and professional. "
        "You NEVER include invitations, calls-to-action, RSVP, registration, links, venue/logistics, or future marketing copy."
    )

    prompt = f"""
Create a SHORT post-event recap in STRICT JSON. English only. Past tense.

Meeting:
- Title: {title}
- Date: {date}
- Theme: {topic}

Agenda (with timestamps):
{ag_lines}

KPIs (if any, verbatim list):
{kpi_lines}

Write:
- headline: <= 8 words, clear summary of the session (no invites).
- subheadline: <= 12 words, context like date/theme (no invites).
- bullets: 4–6 items, each <= 18 words, focused on outcomes/insights/what we achieved.
- If you mention KPIs, tie them concretely to agenda topics.
- Absolutely NO invitations, no “join us/our/the…”, no “register/RSVP”, no links, no “see you there”.

JSON SCHEMA (strict):
{{
  "headline": "string",
  "subheadline": "string",
  "bullets": ["string", "string", "string", "string"]
}}

Output ONLY JSON, nothing else.
"""

    try:
        resp = client.chat.completions.create(
            model=LM_MODEL_ID,
            messages=[{"role":"system","content":system},{"role":"user","content":prompt}],
            temperature=0.3,
        )
        raw = (resp.choices[0].message.content or "").strip()
        data = _json_loads_safe(_extract_json_block(raw))
        # fallback sanity
        headline = (data.get("headline") or title).strip()
        sub = (data.get("subheadline") or f"{date} · {topic}".strip()).strip()
        bullets = [str(b).strip() for b in (data.get("bullets") or []) if str(b).strip()]
        # truncate bullets and cap length (defensive)
        bullets = bullets[:6]
        bullets = [ (b if len(b) <= 120 else (b[:117]+"…")) for b in bullets ]
        if len(bullets) < 4:
            # minimal fallback: derive from agenda
            bullets += [f"Covered: {a.get('title','')}" for a in agenda][: (4 - len(bullets))]
        return {"headline": headline, "subheadline": sub, "bullets": bullets}
    except Exception as e:
        # very small fallback
        return {
            "headline": title,
            "subheadline": f"{date} · {topic}".strip(),
            "bullets": [a.get("title","") for a in agenda][:4] or ["Key outcomes shared."]
        }

def generate_ai_report_content(prompt: str, data: Dict[str, Any]) -> str:
    """
    Generate AI report content using LLM based on meeting data
    """
    try:
        response = client.chat.completions.create(
            model=LM_MODEL_ID,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert business analyst specializing in QA leadership and team performance. Generate comprehensive, professional reports based on meeting data. Focus on actionable insights, clear metrics, and strategic recommendations."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.7,
            max_tokens=2000
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        print(f"Error generating AI report: {e}")
        return f"Error generating report: {str(e)}"
