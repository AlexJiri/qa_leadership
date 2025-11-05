from flask import Flask, request, jsonify, render_template, send_from_directory, render_template_string, url_for, make_response, redirect, abort
from flask_cors import CORS
import json
import os
import time
import random
import secrets
import shutil
import datetime
import glob

# AI + PPT (LM Studio in gpt_utils)
from utils.gpt_utils import match_kpis_with_ai, generate_newsletter_ai, generate_newsletter_overlay
from utils.ppt_generator import generate_pptx_report

# QR local
import qrcode
from markupsafe import escape  # to safely display title in HTML

# ========== APP ==========
app = Flask(__name__, static_url_path="/static", static_folder="static", template_folder="templates")
CORS(app)

# ======================================
# Mini "storage" pe disc (un singur JSON)
# ======================================
DATA_FILE = "data.json"

default_structure = {
    "members": [],
    "kpis": [],
    "meetings": [],
    "debates": [],  # list – each contains signups/format/flow/rubric/scores/live
    "quizzes": [],  # list – each contains questions/answers/scores
    "quiz_sessions": [],  # live quiz sessions (admin + players + state)
    "feedback_forms": []  # << NEW
}

def ensure_data_file():
    """Ensure data.json exists and has required structure. NEVER overwrites existing data."""
    if not os.path.exists(DATA_FILE):
        # Only create new file if it doesn't exist
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(default_structure, f, ensure_ascii=False, indent=2)
        return
    
    # File exists - read it carefully
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        if not isinstance(data, dict):
            # File is corrupted but exists - create backup and raise error
            backup_name = f"{DATA_FILE}.corrupted.{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
            try:
                shutil.copy2(DATA_FILE, backup_name)
                print(f"ERROR: {DATA_FILE} is corrupted. Created backup: {backup_name}")
            except:
                pass
            raise ValueError(f"Invalid JSON structure in {DATA_FILE}. Backup created: {backup_name}")
        
        # Add missing keys without overwriting existing data
        changed = False
        for k, v in default_structure.items():
            if k not in data:
                data[k] = v
                changed = True
        
        # Only save if we added missing keys (not if file was corrupted)
        if changed:
            # Create backup before modifying
            backup_name = f"{DATA_FILE}.before_add_keys.{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
            try:
                shutil.copy2(DATA_FILE, backup_name)
            except:
                pass
            
            with open(DATA_FILE, "w", encoding="utf-8") as wf:
                json.dump(data, wf, ensure_ascii=False, indent=2)
    
    except json.JSONDecodeError as e:
        # JSON parsing error - file is corrupted
        backup_name = f"{DATA_FILE}.corrupted.{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        try:
            shutil.copy2(DATA_FILE, backup_name)
            print(f"ERROR: JSON decode error in {DATA_FILE}. Created backup: {backup_name}")
        except:
            pass
        # DON'T overwrite - raise error so user knows
        raise ValueError(f"JSON decode error in {DATA_FILE}. Backup created: {backup_name}. Original error: {e}")
    
    except Exception as e:
        # Any other error - create backup and raise
        backup_name = f"{DATA_FILE}.error.{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        try:
            shutil.copy2(DATA_FILE, backup_name)
            print(f"ERROR reading {DATA_FILE}: {e}. Created backup: {backup_name}")
        except:
            pass
        # NEVER overwrite existing data - raise error instead
        raise ValueError(f"Error reading {DATA_FILE}. Backup created: {backup_name}. Original error: {e}")

def load_data():
    ensure_data_file()
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    """Save data to file with automatic backup before writing"""
    # Create backup before saving (only if file exists and has data)
    if os.path.exists(DATA_FILE):
        try:
            # Check if file has meaningful data (more than just empty structure)
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
                total_items = sum(len(v) if isinstance(v, list) else 1 for v in existing_data.values())
                
                # Only backup if file has data
                if total_items > 0:
                    backup_name = f"{DATA_FILE}.backup.{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    shutil.copy2(DATA_FILE, backup_name)
                    # Keep only last 10 backups to avoid disk space issues
                    try:
                        backups = sorted(glob.glob(f"{DATA_FILE}.backup.*"), reverse=True)
                        for old_backup in backups[10:]:  # Keep last 10
                            try:
                                os.remove(old_backup)
                            except:
                                pass
                    except:
                        pass
        except:
            # If we can't read existing file, still try to save (might be corrupted)
            pass
    
    # Save data
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        # If save fails, try to restore from backup
        backups = sorted(glob.glob(f"{DATA_FILE}.backup.*"), reverse=True)
        if backups:
            print(f"ERROR saving {DATA_FILE}: {e}. Attempting to restore from latest backup...")
            try:
                shutil.copy2(backups[0], DATA_FILE)
                print(f"Restored from backup: {backups[0]}")
            except:
                pass
        raise e

# ---------- UI ----------
@app.route("/")
def index():
    return render_template("index.html")

# dedicated UI page for Debate (admin)
@app.route("/debate")
def debate_page():
    return render_template("debate.html")

# dedicated UI page for Rewards/Leaderboard

# separate page for Live Debate (timer + live score)
# IMPORTANT: we have both URL patterns to avoid 404
@app.route("/live/<did>")
@app.route("/debates/<did>/live")
def live_page(did):
    # just template; data is fetched via API from frontend
    data = load_data()
    debate = next((d for d in data.get("debates", []) if str(d.get("id")) == str(did)), None)
    if not debate:
        abort(404)
    # optional: if not finished and not yet live, mark it live here
    if debate.get("status") not in ("live", "finished"):
        debate["status"] = "live"
        # start live.active
        live = debate.get("live") or {}
        live["active"] = True
        live["started_at"] = live.get("started_at") or int(time.time())
        debate["live"] = live
        # persist
        debates = data.get("debates", [])
        for i, db in enumerate(debates):
            if str(db.get("id")) == str(did):
                debates[i] = debate
                break
        data["debates"] = debates
        save_data(data)
    return render_template("live.html", did=str(did))

# ---------- Membri CRUD ----------
@app.route("/api/members", methods=["GET", "POST"])
def members():
    try:
        data = load_data()
        if request.method == "POST":
            payload = request.json or {}
            name = payload.get("name", "").strip()
            email = (payload.get("email", "") or "").strip().lower()
            studio = payload.get("studio", "CC")
            status = payload.get("status", "active")
            clan_lead = payload.get("clan_lead", False)
            if not name or not email:
                return jsonify({"error": "Name and email required"}), 400
            data["members"].append({
                "name": name, "email": email, "studio": studio, "status": status, "clan_lead": clan_lead, "external": payload.get("external", False)
            })
            save_data(data)
            return jsonify({"status": "saved"}), 200
        return jsonify(data.get("members", []))
    except Exception as e:
        print("ERROR /api/members:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/members/<int:member_id>", methods=["PUT", "DELETE"])
def modify_member(member_id: int):
    try:
        data = load_data()
        members = data.get("members", [])
        if member_id < 0 or member_id >= len(members):
                            return jsonify({"error": "Invalid index"}), 404

        if request.method == "PUT":
            payload = request.json or {}
            members[member_id]["name"] = payload.get("name", members[member_id]["name"])
            members[member_id]["email"] = (payload.get("email", members[member_id]["email"]) or "").lower()
            members[member_id]["studio"] = payload.get("studio", members[member_id]["studio"])
            members[member_id]["status"] = payload.get("status", members[member_id]["status"])
            members[member_id]["clan_lead"] = payload.get("clan_lead", members[member_id].get("clan_lead", False))
            members[member_id]["external"] = payload.get("external", members[member_id].get("external", False))
            data["members"] = members
            save_data(data)
            return jsonify({"status": "updated"}), 200

        # DELETE
        removed = members.pop(member_id)
        data["members"] = members
        save_data(data)
        return jsonify({"status": "deleted", "removed": removed}), 200

    except Exception as e:
        print("ERROR PUT/DELETE /api/members/<id>:", e)
        return jsonify({"error": str(e)}), 500

# ---------- KPI CRUD ----------
# Initialize kpi_categories if it doesn't exist
@app.route("/api/kpis/init", methods=["POST"])
def init_kpis():
    try:
        data = load_data()
        if "kpi_categories" not in data:
            data["kpi_categories"] = []
        save_data(data)
        return jsonify({"status": "initialized"}), 200
    except Exception as e:
        print("ERROR /api/kpis/init:", e)
        return jsonify({"error": str(e)}), 500

# Categories CRUD
@app.route("/api/kpi-categories", methods=["GET", "POST"])
def kpi_categories():
    try:
        data = load_data()
        if "kpi_categories" not in data:
            data["kpi_categories"] = []
            save_data(data)
        
        if request.method == "POST":
            payload = request.json or {}
            category_name = (payload.get("name") or "").strip()
            if not category_name:
                return jsonify({"error": "Empty category name"}), 400
            # Check if category already exists
            for cat in data["kpi_categories"]:
                if cat.get("name") == category_name:
                    return jsonify({"error": "Category already exists"}), 400
            new_category = {
                "id": len(data["kpi_categories"]),
                "name": category_name,
                "kpis": []
            }
            data["kpi_categories"].append(new_category)
            save_data(data)
            return jsonify({"status": "saved", "category": new_category}), 200
        
        return jsonify(data.get("kpi_categories", []))
    except Exception as e:
        print("ERROR /api/kpi-categories:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/kpi-categories/<int:category_id>", methods=["PUT", "DELETE"])
def modify_kpi_category(category_id: int):
    try:
        data = load_data()
        categories = data.get("kpi_categories", [])
        category = next((c for c in categories if c.get("id") == category_id), None)
        
        if not category:
            return jsonify({"error": "Category not found"}), 404

        if request.method == "PUT":
            payload = request.json or {}
            new_name = (payload.get("name") or "").strip()
            if not new_name:
                return jsonify({"error": "Empty category name"}), 400
            category["name"] = new_name
            save_data(data)
            return jsonify({"status": "updated"}), 200

        # DELETE
        data["kpi_categories"] = [c for c in categories if c.get("id") != category_id]
        save_data(data)
        return jsonify({"status": "deleted"}), 200

    except Exception as e:
        print("ERROR PUT/DELETE /api/kpi-categories/<id>:", e)
        return jsonify({"error": str(e)}), 500

# KPI items CRUD within a category
@app.route("/api/kpi-categories/<int:category_id>/kpis", methods=["POST"])
def add_kpi_to_category(category_id: int):
    try:
        data = load_data()
        categories = data.get("kpi_categories", [])
        category = next((c for c in categories if c.get("id") == category_id), None)
        
        if not category:
            return jsonify({"error": "Category not found"}), 404

        payload = request.json or {}
        name = (payload.get("name") or "").strip()
        how_to_measure = (payload.get("how_to_measure") or "").strip()
        
        if not name or not how_to_measure:
            return jsonify({"error": "Name and how to measure are required"}), 400
        
        new_kpi = {
            "id": len(category.get("kpis", [])),
            "name": name,
            "how_to_measure": how_to_measure
        }
        category.setdefault("kpis", []).append(new_kpi)
        save_data(data)
        return jsonify({"status": "saved", "kpi": new_kpi}), 200
        
    except Exception as e:
        print("ERROR POST /api/kpi-categories/<id>/kpis:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/kpi-categories/<int:category_id>/kpis/<int:kpi_id>", methods=["PUT", "DELETE"])
def modify_kpi_in_category(category_id: int, kpi_id: int):
    try:
        data = load_data()
        categories = data.get("kpi_categories", [])
        category = next((c for c in categories if c.get("id") == category_id), None)
        
        if not category:
            return jsonify({"error": "Category not found"}), 404
        
        kpis = category.get("kpis", [])
        kpi = next((k for k in kpis if k.get("id") == kpi_id), None)
        
        if not kpi:
            return jsonify({"error": "KPI not found"}), 404

        if request.method == "PUT":
            payload = request.json or {}
            name = (payload.get("name") or "").strip()
            how_to_measure = (payload.get("how_to_measure") or "").strip()
            
            if not name or not how_to_measure:
                return jsonify({"error": "Name and how to measure are required"}), 400
            
            kpi["name"] = name
            kpi["how_to_measure"] = how_to_measure
            save_data(data)
            return jsonify({"status": "updated"}), 200

        # DELETE
        category["kpis"] = [k for k in kpis if k.get("id") != kpi_id]
        save_data(data)
        return jsonify({"status": "deleted"}), 200

    except Exception as e:
        print("ERROR PUT/DELETE /api/kpi-categories/<id>/kpis/<id>:", e)
        return jsonify({"error": str(e)}), 500

# ---------- Meetings CRUD ----------
@app.route("/api/meetings", methods=["GET", "POST", "PUT", "DELETE"])
def meetings():
    try:
        data = load_data()
        if request.method == "POST":
            payload = request.json or {}
            m = {
                "id": int(time.time() * 1000),
                "title": payload.get("title", ""),
                "date": payload.get("date", ""),
                "topic": payload.get("topic", ""),
                "participants": [{"email": e, "name": "", "present": False} for e in payload.get("participants", [])],
                "agenda": payload.get("agenda", []),
                "matched_kpis": payload.get("matched_kpis", []),
                "types": payload.get("types", []),  # Empty array if no features selected
            }
            data["meetings"].append(m)
            save_data(data)
            return jsonify({"status": "saved", "id": m["id"]}), 200

        if request.method == "PUT":
            payload = request.json or {}
            mid = payload.get("id")
            if not mid:
                return jsonify({"error": "Missing id"}), 400
            for idx, mt in enumerate(data.get("meetings", [])):
                if str(mt.get("id")) == str(mid):
                    data["meetings"][idx].update({k: v for k, v in payload.items() if k != "id"})
                    save_data(data)
                    return jsonify({"status": "updated"}), 200
            return jsonify({"error": "Meeting not found"}), 404

        if request.method == "DELETE":
            mid = request.args.get("id")
            if not mid:
                return jsonify({"error": "Missing id"}), 400
            
            # Remove associated points entries for this meeting
            points_entries = data.get("points_entries", [])
            data["points_entries"] = [entry for entry in points_entries if entry.get("meeting_id") != int(mid)]
            
            # Remove the meeting
            ms = data.get("meetings", [])
            ms = [m for m in ms if str(m.get("id")) != str(mid)]
            data["meetings"] = ms
            save_data(data)
            return jsonify({"status": "deleted"}), 200

        # GET
        return jsonify(data.get("meetings", []))

    except Exception as e:
        print("ERROR /api/meetings:", e)
        return jsonify({"error": str(e)}), 500

# ---------- Helpers pentru QR & lookup ----------
def _member_by_email(data, email):
    email = (email or "").strip().lower()
    for m in data.get("members", []):
        if (m.get("email") or "").strip().lower() == email:
            return m
    return None

def _studio_of(data, email):
    m = _member_by_email(data, email) or {}
    return (m.get("studio") or "").strip().upper()

def _participants_by_email_map(meeting):
    out = {}
    for p in (meeting.get("participants") or []):
        em = (p.get("email") or "").strip().lower()
        if em:
            out[em] = p
    return out

def _meeting_by_id(data, mid):
    return next((m for m in data.get("meetings", []) if str(m.get("id")) == str(mid)), None)

def _versioned_qr_png(url, prefix):
    """
    Creates a new version PNG QR (avoids cache) and returns (qr_url, ts).
    """
    ts = int(time.time() * 1000)  # Use milliseconds for better uniqueness
    img = qrcode.make(url)
    os.makedirs("static", exist_ok=True)
    fname = f"static/{prefix}_{ts}.png"
    img.save(fname)
    # Add cache-busting parameter to URL
    qr_url = f"/{fname}?v={ts}"
    return (qr_url, ts)

# ---------- QR check-in pentru meeting (existent) ----------
@app.route("/api/meetings/<mid>/qr", methods=["POST"])
def meeting_qr(mid):
    try:
        checkin_url = url_for("meeting_checkin", mid=mid, _external=True)
        qr_url, _ = _versioned_qr_png(checkin_url, f"qr_{mid}")
        return jsonify({"qr_url": qr_url, "checkin_url": checkin_url})
    except Exception as e:
        print("ERROR /api/meetings/<mid>/qr:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/meetings/<mid>/checkin", methods=["GET", "POST"])
def meeting_checkin(mid):
    """
    Check-in form with email. If email is invited, mark present=True.
    """
    try:
        data = load_data()
        meetings = data.get("meetings", [])
        meeting = next((m for m in meetings if str(m.get("id")) == str(mid)), None)

        if not meeting:
            html = """
            <html><head><meta name="viewport" content="width=device-width, initial-scale=1" />
            <style>
              body{font-family:Arial,sans-serif;background:#f6f7fb;margin:0;padding:24px}
              .card{max-width:560px;margin:0 auto;background:#fff;border:1px solid #eaedf4;border-radius:12px;padding:18px}
              h2{margin:0 0 6px 0}.muted{color:#667}
            </style></head>
            <body><div class="card"><h2>Meeting not found</h2></div></body></html>
            """
            return html, 404

        def want_json():
            if (request.args.get("format") or "").lower() == "json":
                return True
            accept = (request.headers.get("accept") or "").lower()
            return "application/json" in accept

        email = ""
        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
        else:
            email = (request.args.get("email") or "").strip().lower()

        if not email:
            title = escape(meeting.get("title") or "QA Meeting")
            date = escape(meeting.get("date") or "")
            html = f"""
            <html><head><meta name="viewport" content="width=device-width, initial-scale=1" />
            <style>
              body{{font-family:Arial,sans-serif;background:#f6f7fb;margin:0;padding:24px}}
              .card{{max-width:560px;margin:0 auto;background:#fff;border:1px solid #eaedf4;border-radius:12px;padding:18px}}
              h2{{margin:0 0 6px 0}} .muted{{color:#667}}
              form{{margin-top:12px}} input{{width:100%;padding:10px;border:1px solid #d7dbe5;border-radius:8px}}
              .btn{{margin-top:10px;background:#1d2233;color:#fff;border:none;border-radius:8px;padding:10px 14px;cursor:pointer;width:100%}}
            </style></head>
            <body>
              <div class="card">
                <h2>QR Check-in</h2>
                <div class="muted">{title} • {date}</div>
                <form method="GET">
                  <label for="email">Enter your email address:</label>
                  <input id="email" name="email" type="email" placeholder="prenume.nume@companie.com" required />
                  <button class="btn" type="submit">Confirm attendance</button>
                </form>
              </div>
            </body></html>
            """
            return html

        invited = None
        for p in meeting.get("participants", []):
            if (p.get("email") or "").strip().lower() == email:
                invited = p
                break

        if not invited:
            if want_json():
                return jsonify({"error": "Email is not in the invite list"}), 404
            html = """
            <html><head><meta name="viewport" content="width=device-width, initial-scale=1" />
            <style>
              body{font-family:Arial,sans-serif;background:#f6f7fb;margin:0;padding:24px}
              .card{max-width:560px;margin:0 auto;background:#fff;border:1px solid #eaedf4;border-radius:12px;padding:18px}
              h2{margin:0 0 6px 0}.muted{color:#a33}
              a.btn{display:inline-block;margin-top:10px;background:#1d2233;color:#fff;text-decoration:none;border-radius:8px;padding:10px 14px}
            </style></head>
            <body><div class="card"><h2>You are not in the invite list</h2></div></body></html>
            """
            return html, 404

        invited["present"] = True
        for i, m in enumerate(meetings):
            if str(m.get("id")) == str(mid):
                meetings[i] = meeting
                break
        data["meetings"] = meetings
        save_data(data)
        
        # Award attendance points
        award_meeting_attendance_points(meeting)

        if want_json():
            return jsonify({"status": "checked_in", "email": email}), 200

        title = escape(meeting.get("title") or "QA Meeting")
        date = escape(meeting.get("date") or "")
        html = f"""
        <html><head><meta name="viewport" content="width=device-width, initial-scale=1" />
        <style>
          body{{font-family:Arial,sans-serif;background:#f6f7fb;margin:0;padding:24px}}
          .card{{max-width:560px;margin:0 auto;background:#fff;border:1px solid #eaedf4;border-radius:12px;padding:18px;text-align:center}}
          h2{{margin:0 0 6px 0}} .ok{{color:#166534}}
          .muted{{color:#667}}
        </style></head>
        <body>
          <div class="card">
            <h2 class="ok">Check-in confirmed ✅</h2>
            <div class="muted">{title} • {date}</div>
            <p>Thank you! Your attendance has been recorded.</p>
          </div>
        </body></html>
        """
        return html

    except Exception as e:
        print("ERROR /api/meetings/<mid>/checkin:", e)
        if (request.args.get("format") or "").lower() == "json":
            return jsonify({"error": str(e)}), 500
        return make_response("An error occurred. Please try again.", 500)

# ---------- Debates helpers ----------
def _ensure_live_shape(debate: dict):
    live = debate.get("live")
    if not isinstance(live, dict):
        live = {"active": False, "started_at": None}
    else:
        live.setdefault("active", False)
        live.setdefault("started_at", None)
    debate["live"] = live
    return debate

def _gen_step_qrs_for_debate(debate):
    """
    For each step in flow with action in {"jury_vote","public_vote"}:
      - builds step URL (unique per debate + index)
      - generates new version PNG
      - saves in step["qr"] = { "url": <link>, "qr_url": <img>, "ts": <int>, "type": "jury|public" }
    """
    try:
        did = debate.get("id")
        flow = debate.get("flow") or []
        for i, st in enumerate(flow):
            action = (st.get("action") or "none").lower()
            if action not in ("jury_vote", "simple_jury_vote", "public_vote", "jury+public", "simple_jury+public"):
                st.pop("qr", None)
                continue
            
            if action in ("jury_vote", "simple_jury_vote"):
                link = url_for("jury_vote_page", did=did, _external=True) + f"?step={i}"
                qr_url, ts = _versioned_qr_png(link, f"qr_stepjury_{did}_{i}")
                st["qr"] = {"url": link, "qr_url": qr_url, "ts": ts, "type": "jury"}
            elif action == "public_vote":
                link = url_for("public_vote_page", did=did, _external=True) + f"?step={i}"
                qr_url, ts = _versioned_qr_png(link, f"qr_steppub_{did}_{i}")
                st["qr"] = {"url": link, "qr_url": qr_url, "ts": ts, "type": "public"}
            elif action in ("jury+public", "simple_jury+public"):
                # Generate both jury and public QR codes
                jury_link = url_for("jury_vote_page", did=did, _external=True) + f"?step={i}"
                public_link = url_for("public_vote_page", did=did, _external=True) + f"?step={i}"
                jury_qr_url, jury_ts = _versioned_qr_png(jury_link, f"qr_stepjury_{did}_{i}")
                public_qr_url, public_ts = _versioned_qr_png(public_link, f"qr_steppub_{did}_{i}")
                st["qr"] = {
                    "url": jury_link,  # Default to jury link for compatibility
                    "qr_url": jury_qr_url,  # Default to jury QR for compatibility
                    "ts": jury_ts,
                    "type": "jury+public",
                    "jury": {"url": jury_link, "qr_url": jury_qr_url, "ts": jury_ts},
                    "public": {"url": public_link, "qr_url": public_qr_url, "ts": public_ts}
                }
        debate["flow"] = flow
    except Exception as e:
        print("WARN gen_step_qrs:", e)

def _compute_totals(debate: dict):
    """Calculates team totals from current scores (jury rubric + public)."""
    totals = {}
    for t in debate.get("teams", []) or []:
        tid = t.get("id")
        if tid:
            totals[tid] = 0.0

    scores = debate.get("scores") or {}
    jury = scores.get("jury") or {}
    for step_map in jury.values():
        for judge_map in (step_map or {}).values():
            for team_id, crits in (judge_map or {}).items():
                if "default" in crits:
                    # Simple team choice - give 1 point
                    try:
                        totals[team_id] = totals.get(team_id, 0.0) + float(crits["default"])
                    except Exception:
                        pass
                else:
                    # Rubric scoring
                    for v in (crits or {}).values():
                        try:
                            totals[team_id] = totals.get(team_id, 0.0) + float(v)
                        except Exception:
                            pass

    public = scores.get("public") or {}
    for step_map in public.values():
        if not step_map:
            continue
        
        # Find team with most public votes for this step
        team_votes = {}
        for team_id, val in step_map.items():
            if team_id == "_voters":
                continue
            try:
                team_votes[team_id] = float(val)
            except Exception:
                pass
        
        if team_votes:
            # Give 1 point to team(s) with most votes for this step only
            max_votes = max(team_votes.values()) if team_votes else 0
            if max_votes > 0:
                for team_id, votes in team_votes.items():
                    if votes == max_votes:
                        totals[team_id] = totals.get(team_id, 0.0) + 1.0

    return totals

# ---------- Debates CRUD (Flow + rubric + format + signups + scores) ----------
@app.route("/api/debates", methods=["GET", "POST", "PUT", "DELETE"])
def debates():
    try:
        data = load_data()
        data.setdefault("debates", [])

        if request.method == "POST":
            p = request.json or {}
            d = {
                "id": int(time.time() * 1000),
                "affirmation": p.get("affirmation", ""),
                "meeting_id": p.get("meeting_id"),
                "prize": p.get("prize", ""),
                # teams / judges – edited in Live
                "judges": p.get("judges", []),          # emails
                "teams": p.get("teams", []),            # [{id,name,members:[emails]}]
                "reserves": p.get("reserves", []),      # [emails]
                # flow & rubric
                "flow": p.get("flow", []),              # [{title,duration_sec,action,qr?}]
                "rubric": p.get("rubric", []),          # [{key,label,min,max}]
                # scores on new structure:
                # scores = {"jury": {step: {judge_email: {team_id: {crit: val}}}},
                #           "public": {step: {team_id: votes}}}
                "scores": p.get("scores", {"jury":{}, "public":{}}),
                "status": p.get("status", "planned"),   # planned / live / finished
                "format": p.get("format", {
                    "team_count": 2, "team_size": 2, "judge_count": 2
                }),
                "rounds": p.get("rounds", []),              # [{number, title, description}]
                "signups": p.get("signups", {}),        # {email: {"choice": "judge|advocate|any|none", "ts": int}}
                "created_at": int(time.time())
            }
            _ensure_live_shape(d)
            # generate flow QRs for voting steps
            _gen_step_qrs_for_debate(d)
            data["debates"].append(d)
            save_data(data)
            return jsonify({"status": "saved", "id": d["id"]}), 200

        if request.method == "PUT":
            p = request.json or {}
            did = p.get("id")
            if not did:
                return jsonify({"error": "Missing id"}), 400
            found = False
            debates_list = data.get("debates", [])
            for i, db in enumerate(debates_list):
                if str(db.get("id")) == str(did):
                    # update fields
                    for k, v in p.items():
                        if k == "id":
                            continue
                        debates_list[i][k] = v
                    _ensure_live_shape(debates_list[i])
                    # regen flow QRs (in case new steps were added)
                    _gen_step_qrs_for_debate(debates_list[i])
                    found = True
                    break
            if not found:
                return jsonify({"error": "Debate not found"}), 404
            data["debates"] = debates_list
            save_data(data)
            return jsonify({"status": "updated"}), 200

        if request.method == "DELETE":
            did = request.args.get("id")
            if not did:
                return jsonify({"error": "Missing id"}), 400
            
            # Remove associated points entries for this debate
            points_entries = data.get("points_entries", [])
            data["points_entries"] = [entry for entry in points_entries if entry.get("debate_id") != int(did)]
            
            # Remove the debate
            data["debates"] = [x for x in data.get("debates", []) if str(x.get("id")) != str(did)]
            save_data(data)
            return jsonify({"status": "deleted"}), 200

        # GET – list
        return jsonify(data.get("debates", []))
    except Exception as e:
        print("ERROR /api/debates:", e)
        return jsonify({"error": str(e)}), 500

# GET un singur debate (util pentru live.html)
@app.route("/api/debates/<did>", methods=["GET"])
def get_debate(did):
    try:
        data = load_data()
        d = next((x for x in data.get("debates", []) if str(x.get("id")) == str(did)), None)
        if not d:
            return jsonify({"error": "Debate not found"}), 404
        _ensure_live_shape(d)
        return jsonify(d)
    except Exception as e:
        print("ERROR /api/debates/<did>:", e)
        return jsonify({"error": str(e)}), 500

# ---------- Registration (QR + page + listare) ----------
@app.route("/api/debates/<did>/registration-qr", methods=["POST"])
def debate_registration_qr(did):
    try:
        data = load_data()
        debate = next((d for d in data.get("debates", []) if str(d.get("id")) == str(did)), None)
        if not debate:
            return jsonify({"error": "Debate not found"}), 404
        reg_url = url_for("debate_register_page", did=did, _external=True)
        qr_url, ts = _versioned_qr_png(reg_url, f"qr_reg_{did}")
        debate["registration_qr"] = {"url": reg_url, "qr_url": qr_url, "ts": ts}
        for i, d in enumerate(data["debates"]):
            if str(d.get("id")) == str(did):
                data["debates"][i] = debate
                break
        save_data(data)
        return jsonify({"qr_url": qr_url, "reg_url": reg_url, "ts": ts, "form_url": reg_url})
    except Exception as e:
        print("ERROR /api/debates/<did>/registration-qr:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/debates/<did>/register", methods=["GET", "POST"])
def debate_register_page(did):
    try:
        data = load_data()
        debate = next((d for d in data.get("debates", []) if str(d.get("id")) == str(did)), None)
        if not debate:
            return make_response("Debate not found", 404)

        message = ""
        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
            choice = (request.form.get("choice") or "none").strip().lower()
            if not email:
                message = "Please enter a valid email."
            else:
                signups = debate.get("signups") or {}
                signups[email] = {"choice": choice, "ts": int(time.time())}
                debate["signups"] = signups
                for i, d in enumerate(data["debates"]):
                    if str(d.get("id")) == str(did):
                        data["debates"][i] = debate
                        break
                save_data(data)
                message = "Registration recorded. Thank you!"

        html = render_template_string("""
        <!DOCTYPE html><html><head>
        <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Debate registration</title>
        <style>
          body{font-family:Arial,sans-serif;background:#f6f7fb;margin:0;padding:24px}
          .card{max-width:560px;margin:0 auto;background:#fff;border:1px solid #eaedf4;border-radius:12px;padding:18px}
          h2{margin:0 0 6px 0}.muted{color:#667}
          input,select,button{padding:10px;border:1px solid #d7dbe5;border-radius:8px;width:100%}
          button{background:#1d2233;color:#fff;cursor:pointer}
          .msg{margin:8px 0;color:#166534}
        </style></head><body>
          <div class="card">
            <h2>Debate registration</h2>
            <div class="muted">{{ aff }}</div>
            {% if message %}<div class="msg">{{ message }}</div>{% endif %}
            <form method="POST">
              <label>Email</label>
              <input name="email" type="email" placeholder="prenume.nume@companie.com" required />
              <div style="height:10px"></div>
              <label>Rol dorit</label>
              <select name="choice">
                <option value="advocate">I want to participate as advocate</option>
                <option value="judge">I want to participate as judge</option>
                <option value="any">I want to participate in any role</option>
                <option value="none">I don't want to participate</option>
              </select>
              <div style="height:12px"></div>
              <button type="submit">Submit</button>
            </form>
          </div>
        </body></html>
        """, aff=(debate.get("affirmation") or "Debate"), message=message)
        return html
    except Exception as e:
        print("ERROR /debates/<did>/register:", e)
        return make_response("Error", 500)

@app.route("/api/debates/<did>/signups", methods=["GET"])
def debate_signups(did):
    try:
        data = load_data()
        debate = next((d for d in data.get("debates", []) if str(d.get("id")) == str(did)), None)
        if not debate:
            return jsonify({"error": "Debate not found"}), 404
        return jsonify(debate.get("signups") or {})
    except Exception as e:
        print("ERROR /api/debates/<did>/signups:", e)
        return jsonify({"error": str(e)}), 500

# ---------- Randomize (teams/judges) ----------
@app.route("/api/debates/<did>/randomize", methods=["POST"])
def debate_randomize(did):
    import random
    try:
        data = load_data()
        debates = data.get("debates", [])
        debate = next((d for d in debates if str(d.get("id")) == str(did)), None)
        if not debate:
            return jsonify({"error": "Debate not found"}), 404

        def _pmail(s): return (s or "").strip().lower()

        def _participations_count(email: str) -> int:
            em = _pmail(email)
            cnt = 0
            for d in data.get("debates", []):
                if any(_pmail(x) == em for x in d.get("judges", []) or []):
                    cnt += 1
                for t in d.get("teams", []) or []:
                    if any(_pmail(x) == em for x in t.get("members", []) or []):
                        cnt += 1
                if any(_pmail(x) == em for x in d.get("reserves", []) or []):
                    cnt += 1
            return cnt

        def sort_key(email: str):
            return (_participations_count(email), random.random())

        fmt = debate.get("format") or {"team_count": 2, "team_size": 2, "judge_count": 2}
        team_count = int(fmt.get("team_count", 2))
        team_size = int(fmt.get("team_size", 2))
        judge_count = int(fmt.get("judge_count", 2))
        total_slots = team_count * team_size

        signups = debate.get("signups") or {}
        def eligible(e): return _member_by_email(data, e) is not None

        # Separate pools based on signup choices
        judges_only = [e for e, info in signups.items()
                      if info.get("choice") == "judge" and eligible(e)]
        advocates_only = [e for e, info in signups.items()
                         if info.get("choice") == "advocate" and eligible(e)]
        any_role = [e for e, info in signups.items()
                   if info.get("choice") == "any" and eligible(e)]
        
        # Create separate pools respecting participant choices
        # Judges can be: judges_only + any_role
        judges_pool = judges_only + any_role
        judges_pool = list(dict.fromkeys(judges_pool))  # remove duplicates
        
        # Advocates can be: advocates_only + any_role  
        advocates_pool = advocates_only + any_role
        advocates_pool = list(dict.fromkeys(advocates_pool))  # remove duplicates
        
        # Sort by participation count (fewer participations = higher priority)
        judges_pool.sort(key=sort_key)
        advocates_pool.sort(key=sort_key)
        
        # Randomize each pool to ensure equal chances within each role
        random.shuffle(judges_pool)
        random.shuffle(advocates_pool)

        # Check if we have enough members for both judges and teams
        # We need to ensure that after selecting judges, we still have enough advocates for teams
        all_eligible = judges_only + advocates_only + any_role
        all_eligible = list(dict.fromkeys(all_eligible))  # remove duplicates
        
        if len(all_eligible) < total_slots + judge_count:
            return jsonify({"error": f"Insufficient members registered (need {total_slots + judge_count}, we have {len(all_eligible)})"}), 400
        
        # More precise check: ensure we have enough advocates after potential judge selection
        # Judges are selected from judges_only + any_role
        # Advocates are selected from advocates_only + any_role
        # Calculate how many any_role members might be used for judges
        judges_from_any_role = max(0, judge_count - len(judges_only))
        advocates_available = len(advocates_only) + len(any_role) - judges_from_any_role
        if advocates_available < total_slots:
            return jsonify({"error": f"Insufficient advocates after judge selection (need {total_slots}, will have {advocates_available})"}), 400
        
        if len(judges_pool) < judge_count:
            return jsonify({"error": f"Insufficient judges registered (min {judge_count}, we have {len(judges_pool)})"}), 400

        # Select judges with balanced CC/WSOP distribution
        cc_judges = [e for e in judges_pool if _studio_of(data, e) == "CC"]
        ws_judges = [e for e in judges_pool if _studio_of(data, e) == "WSOP"]
        ot_judges = [e for e in judges_pool if _studio_of(data, e) not in ("CC","WSOP")]
        
        # Randomize each studio's judges
        random.shuffle(cc_judges)
        random.shuffle(ws_judges)
        random.shuffle(ot_judges)
        
        # Select judges trying to balance CC/WSOP
        # Prioritize judges_only members first, then fill with any_role
        picked_judges = []
        
        # First, try to select from judges_only to minimize impact on advocates_pool
        cc_judges_only = [e for e in cc_judges if e in judges_only]
        ws_judges_only = [e for e in ws_judges if e in judges_only]
        ot_judges_only = [e for e in ot_judges if e in judges_only]
        
        # Select from judges_only first
        cc_judges_only_count = min(len(cc_judges_only), judge_count // 2)
        ws_judges_only_count = min(len(ws_judges_only), judge_count - cc_judges_only_count)
        ot_judges_only_count = judge_count - cc_judges_only_count - ws_judges_only_count
        
        picked_judges.extend(cc_judges_only[:cc_judges_only_count])
        picked_judges.extend(ws_judges_only[:ws_judges_only_count])
        picked_judges.extend(ot_judges_only[:ot_judges_only_count])
        
        # If we still need more judges, fill from any_role
        remaining_judges_needed = judge_count - len(picked_judges)
        if remaining_judges_needed > 0:
            cc_any_remaining = [e for e in cc_judges if e not in picked_judges]
            ws_any_remaining = [e for e in ws_judges if e not in picked_judges]
            ot_any_remaining = [e for e in ot_judges if e not in picked_judges]
            
            # Fill remaining slots from any_role
            cc_any_count = min(len(cc_any_remaining), remaining_judges_needed // 2)
            ws_any_count = min(len(ws_any_remaining), remaining_judges_needed - cc_any_count)
            ot_any_count = remaining_judges_needed - cc_any_count - ws_any_count
            
            picked_judges.extend(cc_any_remaining[:cc_any_count])
            picked_judges.extend(ws_any_remaining[:ws_any_count])
            picked_judges.extend(ot_any_remaining[:ot_any_count])
        
        # Remove selected judges from advocates pool to avoid conflicts
        remaining_advocates = [e for e in advocates_pool if e not in picked_judges]

        # Debug: print available members
        print(f"DEBUG: Total advocates pool: {len(advocates_pool)}")
        print(f"DEBUG: Selected judges: {len(picked_judges)}")
        print(f"DEBUG: Remaining advocates: {len(remaining_advocates)}")
        print(f"DEBUG: Need {total_slots} team members for {team_count} teams of {team_size}")

        # Initialize teams
        teams = (debate.get("teams") or [])[:team_count]
        while len(teams) < team_count:
            idx = len(teams) + 1
            teams.append({"id": f"t{idx}", "name": f"Team {idx}", "members": []})
        for t in teams:
            t["members"] = []

        # Distribute remaining advocates to teams with balanced CC/WSOP
        cc_remaining = [e for e in remaining_advocates if _studio_of(data, e) == "CC"]
        ws_remaining = [e for e in remaining_advocates if _studio_of(data, e) == "WSOP"]
        ot_remaining = [e for e in remaining_advocates if _studio_of(data, e) not in ("CC","WSOP")]
        
        # Randomize each studio's remaining members
        random.shuffle(cc_remaining)
        random.shuffle(ws_remaining)
        random.shuffle(ot_remaining)
        
        # Distribute members round-robin to balance teams
        used = set()
        order = list(range(team_count))
        random.shuffle(order)
        
        def team_counts(t):
            c = sum(1 for e in t["members"] if _studio_of(data, e) == "CC")
            w = sum(1 for e in t["members"] if _studio_of(data, e) == "WSOP")
            return c, w

        # Simple approach: fill teams one by one with remaining advocates
        all_remaining = cc_remaining + ws_remaining + ot_remaining
        random.shuffle(all_remaining)
        
        # Debug: print available members
        print(f"DEBUG: Available members for teams: {len(all_remaining)}")
        print(f"DEBUG: Need {total_slots} members for {team_count} teams of {team_size}")
        
        # Fill each team to team_size
        for t in teams:
            while len(t["members"]) < team_size and all_remaining:
                p = all_remaining.pop(0)
                if p not in used:
                    t["members"].append(p)
                    used.add(p)
                    print(f"DEBUG: Added {p} to team {t['name']} (now {len(t['members'])}/{team_size})")
        
        # Debug: print final team sizes
        print(f"DEBUG: Final team sizes:")
        for i, t in enumerate(teams):
            print(f"  Team {i+1}: {len(t['members'])} members")

        # Verify that all teams have exactly team_size members
        for t in teams:
            if len(t["members"]) < team_size:
                return jsonify({"error": f"Team {t['name']} has only {len(t['members'])} members, need {team_size}"}), 400

        # Calculate reserves from all available members (excluding judges and team members)
        # Reserves don't need to respect studio distribution - just randomize completely
        all_available = judges_only + advocates_only + any_role
        all_used = set(picked_judges) | used
        reserves = [e for e in all_available if e not in all_used]
        # Randomize reserves order completely - studio distribution doesn't matter
        random.shuffle(reserves)

        debate["judges"] = picked_judges
        debate["teams"] = teams
        debate["reserves"] = reserves

        for i, d in enumerate(debates):
            if str(d.get("id")) == str(did):
                debates[i] = debate
                break
        data["debates"] = debates
        save_data(data)

        return jsonify({"ok": True, "judges": picked_judges, "teams": teams, "reserves": reserves})
    except Exception as e:
        print("ERROR /api/debates/<did>/randomize:", e)
        return jsonify({"error": str(e)}), 500

# ---------- Vot PUBLIC (per pas) ----------
@app.route("/debates/<did>/vote", methods=["GET", "POST"])
def public_vote_page(did):
    try:
        data = load_data()
        debate = next((d for d in data.get("debates", []) if str(d.get("id")) == str(did)), None)
        if not debate:
            return make_response("Debate not found", 404)

        step = int(request.values.get("step", "0"))
        flow = debate.get("flow") or []
        if step < 0 or step >= len(flow):
            return make_response("Invalid step", 400)
        action = (flow[step].get("action") or "none")
        if action not in ("public_vote", "jury+public", "simple_jury+public"):
            return make_response("Not a public vote step", 400)

        # meeting invite validation
        meeting = next((m for m in (load_data().get("meetings") or []) if str(m.get("id")) == str(debate.get("meeting_id"))), None)
        invited = _participants_by_email_map(meeting) if meeting else {}

        message = ""
        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
            team_id = (request.form.get("team_id") or "").strip()
            if not email or not team_id:
                message = "Please fill in email + team choice."
            else:
                # email must be invited to meeting (not necessarily check-in)
                if email not in invited:
                    message = "Email is not invited to this meeting."
                else:
                    # don't allow judge or team member to vote as public
                    if email in (debate.get("judges") or []):
                        message = "Jury members cannot vote as public."
                    elif any(email in (t.get("members") or []) for t in (debate.get("teams") or [])):
                        message = "Team members cannot vote as public."
                    else:
                        scores = debate.get("scores") or {}
                        pub = (scores.get("public") or {})
                        step_map = pub.get(str(step)) or {}
                        voters = step_map.get("_voters") or {}
                        prev = voters.get(email)
                        if prev:
                            if prev != team_id:
                                step_map[prev] = max(0, int(step_map.get(prev, 1)) - 1)
                        voters[email] = team_id
                        step_map["_voters"] = voters
                        step_map[team_id] = int(step_map.get(team_id, 0)) + 1
                        pub[str(step)] = step_map
                        scores["public"] = pub
                        debate["scores"] = scores
                        # persist
                        for i, d in enumerate(data["debates"]):
                            if str(d.get("id")) == str(did):
                                data["debates"][i] = debate
                                break
                        save_data(data)
                        message = "Vote recorded. Thank you!"

        teams = debate.get("teams", [])
        step_title = flow[step].get("title") or f"Step {step+1}"
        html = render_template_string("""
        <!DOCTYPE html><html><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Public vote</title>
        <style>
          body{font-family:Arial,sans-serif;background:#f6f7fb;margin:0;padding:24px}
          .card{max-width:560px;margin:0 auto;background:#fff;border:1px solid #eaedf4;border-radius:12px;padding:18px}
          h2{margin:0 0 8px 0}.muted{color:#667}.msg{margin:8px 0;color:#166534}
          select,input,button{padding:10px;border:1px solid #d7dbe5;border-radius:8px;width:100%}
          button{background:#1d2233;color:#fff;cursor:pointer}
        </style></head><body>
          <div class="card">
            <h2>Public vote</h2>
            <div class="muted">{{ aff }} — {{ step_title }}</div>
            {% if message %}<div class="msg">{{ message }}</div>{% endif %}
            <form method="POST">
              <label>Email</label>
              <input name="email" type="email" placeholder="prenume.nume@companie.com" required />
              <div style="height:10px"></div>
              <label>Team</label>
              <select name="team_id">
                {% for t in teams %}<option value="{{ t.id }}">{{ t.name or t.id }}</option>{% endfor %}
              </select>
              <div style="height:12px"></div>
              <button type="submit">Vote</button>
            </form>
          </div>
        </body></html>
        """, aff=(debate.get("affirmation") or "Debate"), teams=teams, message=message, step_title=step_title)
        return html
    except Exception as e:
        print("ERROR /debates/<did>/vote:", e)
        return make_response("Error", 500)

# ---------- JURY Vote (per step, on rubric) ----------
@app.route("/debates/<did>/jury", methods=["GET", "POST"])
def jury_vote_page(did):
    try:
        data = load_data()
        debate = next((d for d in data.get("debates", []) if str(d.get("id")) == str(did)), None)
        if not debate:
            return make_response("Debate not found", 404)

        step = int(request.values.get("step", "0"))
        flow = debate.get("flow") or []
        if step < 0 or step >= len(flow):
            return make_response("Invalid step", 400)
        action = (flow[step].get("action") or "none")
        if action not in ("jury_vote", "jury+public", "simple_jury_vote", "simple_jury+public"):
            return make_response("Not a jury vote step", 400)

        teams = debate.get("teams") or []
        all_rubric = debate.get("rubric") or []
        
        # Filter rubric based on current step's round
        current_step = flow[step]
        current_round = current_step.get("round", "1")
        
        # Get general criteria + criteria for current round
        rubric = []
        for c in all_rubric:
            c_type = c.get("type", "general")
            c_round = c.get("round", "1")
            if c_type == "general" or (c_type == "round" and c_round == current_round):
                rubric.append(c)
        
        # Check if this is simple jury vote (no rubric needed) or complex vote
        is_simple_vote = action in ("simple_jury_vote", "simple_jury+public")
        has_rubric = not is_simple_vote and any(c.get("min") is not None and c.get("max") is not None for c in rubric)

        message = ""
        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
            # validation: email must be in jury
            if email not in (debate.get("judges") or []):
                message = "Email is not in the jury for this debate."
            else:
                # read scores
                scores = debate.get("scores") or {}
                jury = (scores.get("jury") or {})
                step_map = jury.get(str(step)) or {}
                judge_map = {}
                
                if has_rubric:
                    # Complex rubric scoring - parse inputs: name="{team_id}__{crit_key}"
                    for t in teams:
                        t_id = t.get("id")
                        for c in rubric:
                            key = c.get("key")
                            field = f"{t_id}__{key}"
                            raw = request.form.get(field, "")
                            if raw == "":
                                continue
                            try:
                                val = float(raw)
                            except:
                                continue
                            # clamp between min/max
                            minv = float(c.get("min", 0))
                            maxv = float(c.get("max", 10))
                            val = max(minv, min(maxv, val))
                            judge_map.setdefault(t_id, {})[key] = val
                else:
                    # Simple team choice - give 1 point to selected team
                    team_choice = request.form.get("team_choice", "")
                    if team_choice in [t.get("id") for t in teams]:
                        judge_map[team_choice] = {"default": 1.0}
                
                # save for this judge
                step_map[email] = judge_map
                jury[str(step)] = step_map
                scores["jury"] = jury
                debate["scores"] = scores
                # persist
                for i, d in enumerate(data["debates"]):
                    if str(d.get("id")) == str(did):
                        data["debates"][i] = debate
                        break
                save_data(data)
                message = "Vote recorded. Thank you!"

        step_title = flow[step].get("title") or f"Step {step+1}"
        html = render_template_string("""
        <!DOCTYPE html><html><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Jury vote</title>
        <style>
          body{font-family:Arial,sans-serif;background:#f6f7fb;margin:0;padding:24px}
          .card{max-width:760px;margin:0 auto;background:#fff;border:1px solid #eaedf4;border-radius:12px;padding:18px}
          h2{margin:0 0 8px 0}.muted{color:#667}.msg{margin:8px 0;color:#166534}
          table{width:100%;border-collapse:collapse;margin-top:8px}
          th,td{border:1px solid #eef0f6;padding:6px 8px;text-align:left}
          input{width:90px;padding:8px;border:1px solid #d7dbe5;border-radius:8px}
          button{background:#1d2233;color:#fff;border:none;border-radius:8px;padding:10px 14px;cursor:pointer}
          .team-choice{display:flex;gap:12px;margin:12px 0}
          .team-option{flex:1;padding:12px;border:2px solid #eef0f6;border-radius:8px;cursor:pointer;text-align:center;transition:all 0.2s}
          .team-option:hover{background:#f8fafc;border-color:#1d2233}
          .team-option input{display:none}
          .team-option.selected{background:#1d2233;color:#fff;border-color:#1d2233}
        </style></head><body>
          <div class="card">
            <h2>Jury vote</h2>
            <div class="muted">{{ aff }} — {{ step_title }}</div>
            {% if message %}<div class="msg">{{ message }}</div>{% endif %}
            <form method="POST">
              <label>Email (jurat)</label>
              <input name="email" type="email" placeholder="prenume.nume@companie.com" required style="width:100%;margin-bottom:10px">
              
              {% if has_rubric %}
              <table>
                <thead>
                  <tr>
                    <th>Team</th>
                    {% for c in rubric %}
                      <th>{{ c.label }} <small>(min {{ c.min }}, max {{ c.max }})</small></th>
                    {% endfor %}
                  </tr>
                </thead>
                <tbody>
                  {% for t in teams %}
                    <tr>
                      <td>{{ t.name or t.id }}</td>
                      {% for c in rubric %}
                        <td><input name="{{ t.id }}__{{ c.key }}" type="number" step="0.1" min="{{ c.min }}" max="{{ c.max }}"></td>
                      {% endfor %}
                    </tr>
                  {% endfor %}
                </tbody>
              </table>
              {% else %}
              <div style="margin:16px 0">
                {% if is_simple_vote and rubric %}
                <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px;margin-bottom:16px">
                  <h4 style="margin:0 0 8px 0;color:#1e40af">Evaluation Criteria (for reference):</h4>
                  <ul style="margin:0;padding-left:20px;color:#475569">
                    {% for c in rubric %}
                      <li><strong>{{ c.label }}</strong> - {{ c.key }}</li>
                    {% endfor %}
                  </ul>
                  <p style="margin:8px 0 0 0;font-size:12px;color:#666">Use these criteria to guide your decision, then choose the winning team below.</p>
                </div>
                {% endif %}
                <label style="display:block;margin-bottom:8px;font-weight:600">Choose the winning team:</label>
                <div class="team-choice">
                  {% for t in teams %}
                    <label class="team-option" onclick="selectTeam('{{ t.id }}')">
                      <input type="radio" name="team_choice" value="{{ t.id }}" required>
                      <div style="font-weight:600">{{ t.name or t.id }}</div>
                    </label>
                  {% endfor %}
                </div>
              </div>
              {% endif %}
              <div style="height:10px"></div>
              <button type="submit">Submit scores</button>
            </form>
          </div>
          <script>
            function selectTeam(teamId) {
              document.querySelectorAll('.team-option').forEach(opt => opt.classList.remove('selected'));
              document.querySelector(`input[value="${teamId}"]`).closest('.team-option').classList.add('selected');
            }
          </script>
        </body></html>
        """, aff=(debate.get("affirmation") or "Debate"),
             teams=teams, rubric=rubric, message=message, step_title=step_title, has_rubric=has_rubric, is_simple_vote=is_simple_vote)
        return html
    except Exception as e:
        print("ERROR /debates/<did>/jury:", e)
        return make_response("Error", 500)

# ---------- Live state & scor live ----------
@app.route("/api/debates/<did>/live/start", methods=["POST"])
def live_start(did):
    try:
        data = load_data()
        debates = data.get("debates", [])
        for i, d in enumerate(debates):
            if str(d.get("id")) == str(did):
                _ensure_live_shape(d)
                d["live"]["active"] = True
                d["live"]["started_at"] = int(time.time())
                d["status"] = "live"
                debates[i] = d
                data["debates"] = debates
                save_data(data)
                return jsonify({"ok": True, "live": d["live"]})
        return jsonify({"error": "Debate not found"}), 404
    except Exception as e:
        print("ERROR /api/debates/<did>/live/start:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/debates/<did>/live/stop", methods=["POST"])
def live_stop(did):
    try:
        data = load_data()
        debates = data.get("debates", [])
        for i, d in enumerate(debates):
            if str(d.get("id")) == str(did):
                _ensure_live_shape(d)
                d["live"]["active"] = False
                d["status"] = "finished"
                debates[i] = d
                data["debates"] = debates
                save_data(data)
                
                # Award debate points
                award_debate_points(d)
                
                return jsonify({"ok": True, "live": d["live"]})
        return jsonify({"error": "Debate not found"}), 404
    except Exception as e:
        print("ERROR /api/debates/<did>/live/stop:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/debates/<did>/live", methods=["GET"])
def live_state(did):
    try:
        data = load_data()
        d = next((x for x in data.get("debates", []) if str(x.get("id")) == str(did)), None)
        if not d:
            return jsonify({"error": "Debate not found"}), 404
        _ensure_live_shape(d)
        return jsonify(d.get("live"))
    except Exception as e:
        print("ERROR /api/debates/<did>/live:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/debates/<did>/scores", methods=["GET"])
def live_scores(did):
    """
    Returns real-time score + breakdown, only if live.active=True.
    Frontend (live.html) will do polling ONLY when active=True.
    """
    try:
        data = load_data()
        d = next((x for x in data.get("debates", []) if str(x.get("id")) == str(did)), None)
        if not d:
            return jsonify({"error": "Debate not found"}), 404
        _ensure_live_shape(d)
        active = bool(d.get("live", {}).get("active"))
        resp = {
            "active": active,
            "updated_at": d.get("created_at"),
            "teams": [{"id": t["id"], "name": t.get("name") or t["id"]} for t in (d.get("teams") or [])],
            "totals": _compute_totals(d) if active else {},
            "scores": d.get("scores") if active else {},
        }
        return jsonify(resp)
    except Exception as e:
        print("ERROR /api/debates/<did>/scores:", e)
        return jsonify({"error": str(e)}), 500

# ---------- Simple timer (kept for compatibility / debug) ----------
@app.route("/debates/<did>/timer")
def debate_timer(did):
    return """
<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Debate Timer</title>
<style>
  body{font-family:Arial,sans-serif;background:#0b1220;color:#fff;margin:0;padding:24px;text-align:center}
  .big{font-size:96px;letter-spacing:2px;margin:20px 0}
  .row{display:flex;gap:8px;justify-content:center;flex-wrap:wrap}
  input,button{padding:10px;border-radius:10px;border:1px solid #2b3145;font-size:16px}
  button{background:#1d2233;color:#fff;border:none;cursor:pointer}
</style>
</head><body>
  <h1 style="margin:0">Debate Timer</h1>
  <div id="title" style="opacity:.7">Round timer</div>
  <div class="big" id="clock">00:00</div>
  <div class="row">
    <input id="min" type="number" placeholder="min" style="width:110px">
    <input id="sec" type="number" placeholder="sec" style="width:110px">
    <button id="btnStart">Start</button>
    <button id="btnPause">Pause</button>
    <button id="btnReset">Reset</button>
  </div>
  <script>
    let total=0, left=0, tick=null, running=false;
    const $=s=>document.querySelector(s);
    function fmt(s){ return String(s).padStart(2,'0'); }
    function draw(){ const m=Math.floor(left/60), s=left%60; $('#clock').textContent=fmt(m)+':'+fmt(s); }
    function start(){
      if(left<=0){ const m=+($('#min').value||0), s=+($('#sec').value||0); total=m*60+s; left=total; }
      if(left<=0) return;
      if(tick) clearInterval(tick);
      running=true;
      tick=setInterval(()=>{ left=Math.max(0,left-1); draw(); if(left<=0){ clearInterval(tick); running=false; tick=null; } },1000);
      draw();
    }
    function pause(){ if(tick){ clearInterval(tick); tick=null; running=false; } }
    function reset(){ pause(); left=0; total=0; draw(); }
    $('#btnStart').onclick=start; $('#btnPause').onclick=pause; $('#btnReset').onclick=reset; draw();
  </script>
</body></html>
"""

# ---------- Quiz CRUD ----------
@app.route("/api/quizzes", methods=["GET", "POST", "PUT", "DELETE"])
def quizzes():
    try:
        data = load_data()
        if request.method == "POST":
            payload = request.json or {}
            q = {
                "id": int(time.time() * 1000),
                "meeting_id": payload.get("meeting_id"),
                "title": payload.get("title", ""),
                "status": payload.get("status", "draft"),
                "questions": payload.get("questions", []),
                "created_at": int(time.time() * 1000),
            }
            data["quizzes"].append(q)
            save_data(data)
            return jsonify({"status": "saved", "id": q["id"]}), 200

        if request.method == "PUT":
            payload = request.json or {}
            qid = payload.get("id")
            if not qid:
                return jsonify({"error": "Missing id"}), 400
            for idx, quiz in enumerate(data.get("quizzes", [])):
                if str(quiz.get("id")) == str(qid):
                    data["quizzes"][idx].update({k: v for k, v in payload.items() if k != "id"})
                    save_data(data)
                    return jsonify({"status": "updated"}), 200
            return jsonify({"error": "Quiz not found"}), 404

        if request.method == "DELETE":
            qid = request.args.get("id")
            if not qid:
                return jsonify({"error": "Missing id"}), 400
            quizzes = data.get("quizzes", [])
            quizzes = [q for q in quizzes if str(q.get("id")) != str(qid)]
            data["quizzes"] = quizzes
            save_data(data)
            return jsonify({"status": "deleted"}), 200

        # GET
        return jsonify(data.get("quizzes", []))

    except Exception as e:
        print("ERROR /api/quizzes:", e)
        return jsonify({"error": str(e)}), 500

# ---------- AI (KPI + newsletter HTML existent) ----------
@app.route("/api/kpi-match", methods=["POST"])
def kpi_match():
    try:
        payload = request.json or {}
        result = match_kpis_with_ai(
            payload.get("title", ""),
            payload.get("topic", ""),
            payload.get("agenda", []) or [],
            payload.get("kpis", []) or [],
        )
        return jsonify(result)
    except Exception as e:
        print("ERROR /api/kpi-match:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/newsletter", methods=["POST"])
def newsletter():
    try:
        payload = request.json or {}
        html = generate_newsletter_ai(payload)
        return jsonify({"html": html})
    except Exception as e:
        print("ERROR /api/newsletter:", e)
        return jsonify({"error": str(e)}), 500

# ---------- NOU: AI overlay copy (headline / subheadline / bullets) ----------
from openai import OpenAI
LM_BASE_URL = os.getenv("LM_BASE_URL", "http://127.0.0.1:80/v1")
LM_MODEL_ID = os.getenv("LM_MODEL_ID", "meta-llama-3.1-8b-instruct-128k")
LM_API_KEY  = os.getenv("OPENAI_API_KEY", "lm-studio")
_llm = OpenAI(base_url=LM_BASE_URL, api_key=LM_API_KEY)

def _extract_json_block(text: str) -> str:
    import re
    m = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
    if m: return m.group(1).strip()
    m = re.search(r"```\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
    if m: return m.group(1).strip()
    i = text.find("{"); j = text.rfind("}")
    if i != -1 and j != -1 and j > i: return text[i:j+1].strip()
    raise ValueError("no JSON block")

@app.route("/api/newsletter-overlay", methods=["POST"])
def newsletter_overlay():
    """
    Input: {title, date, topic, agenda:[{start,end,title}], kpis?:[str]}
    Output:  {headline, subheadline, bullets:[str]}
    """
    try:
        payload = request.json or {}
        title = payload.get("title", "")
        date = payload.get("date", "")
        topic = payload.get("topic", "")
        agenda = payload.get("agenda", []) or []
        provided_kpis = [str(x).strip() for x in (payload.get("kpis") or []) if str(x).strip()]

        if not provided_kpis:
            data = load_data()
            # Get all KPIs from all categories and flatten them
            all_kpis = []
            categories = data.get("kpi_categories", [])
            for category in categories:
                if category.get("kpis"):
                    for kpi in category["kpis"]:
                        all_kpis.append(f"{kpi.get('name', '')}: {kpi.get('how_to_measure', '')}")
            # fallback la AI-ul de match deja existent
            match = match_kpis_with_ai(title, topic, [{"title": a.get("title","")} for a in agenda], all_kpis)
            provided_kpis = match.get("matched_kpis") or []

        agenda_lines = "\n".join(
            f"{(a.get('start') or '')}-{(a.get('end') or '')}: {(a.get('title') or '')}".strip("-: ")
            for a in agenda
        ).strip()
        kpi_lines = "\n".join(f"- {k}" for k in provided_kpis).strip() or "—"

        system = (
            "You are a concise copywriter for internal tech newsletters. "
            "Return ONLY valid JSON, no explanations."
        )
        prompt = f"""Create short on-image copy for THIS meeting's internal newsletter recap.
Keep it punchy and scannable. Use ONLY the agenda and KPIs provided (do not invent extra topics).
This is a recap, NOT an invitation; do NOT use 'join us', 'register', 'save the date', or similar.

MEETING
- Title: {title}
- Date: {date}
- Theme: {topic}

AGENDA
{agenda_lines or "—"}

MATCHED KPIs (verbatim; only these are relevant)
{kpi_lines}

RULES
- Strictly follow the JSON schema below. No extra keys.
- <=60 chars for headline, <=80 for subheadline, <=80 per bullet.
- 3–5 bullets max. No emojis. No CTA.

SCHEMA
{{
  "headline": "string",
  "subheadline": "string",
  "bullets": ["string", "string", "string"]
}}
"""

        # Use the dedicated function from gpt_utils
        meeting_data = {
            "title": title,
            "date": date,
            "topic": topic,
            "agenda": agenda,
            "kpis": provided_kpis
        }
        result = generate_newsletter_overlay(meeting_data)
        return jsonify(result)

    except Exception as e:
        print("ERROR /api/newsletter-overlay:", e)
        # fallback simplu
        try:
            payload = request.json or {}
            title = payload.get("title","") or "QA Meeting"
            date  = payload.get("date","")
            topic = payload.get("topic","")
            agenda = payload.get("agenda", []) or []
            bullets = [f"{a.get('start','')}-{a.get('end','')}: {a.get('title','')}" for a in agenda][:4]
            return jsonify({
                "headline": title[:60],
                "subheadline": f"{date} · {topic}".strip(" ·")[:80],
                "bullets": bullets
            })
        except Exception:
            return jsonify({"error": str(e)}), 500

# ==========================================
# ========== REWARDS & POINTS SYSTEM ==========
# ==========================================

# Points system configuration
POINTS_CONFIG = {
    "meeting_attendance": 5,
    "presentation": 15,
    "debate_participant": 5,
    "debate_winner": 15
}

def add_automatic_points(member_email, criteria, reason, meeting_id=None, debate_id=None):
    """Add points automatically based on criteria"""
    try:
        data = load_data()
        
        # Check if member exists
        member = _member_by_email(data, member_email)
        if not member:
            return False
        
        # Skip external members - they don't get points
        if member.get("external", False):
            return False
        
        # Check if points already awarded for this specific event
        points_entries = data.get("points_entries", [])
        existing_entry = None
        
        if meeting_id:
            existing_entry = next((e for e in points_entries 
                                 if e.get("member_email") == member_email 
                                 and e.get("criteria") == criteria 
                                 and e.get("meeting_id") == meeting_id), None)
        elif debate_id:
            existing_entry = next((e for e in points_entries 
                                 if e.get("member_email") == member_email 
                                 and e.get("criteria") == criteria 
                                 and e.get("debate_id") == debate_id), None)
        
        if existing_entry:
            return False  # Already awarded
        
        # Add points entry
        points_entry = {
            "id": int(time.time() * 1000),
            "member_email": member_email,
            "points": POINTS_CONFIG.get(criteria, 0),
            "reason": reason,
            "criteria": criteria,
            "added_by": "system",
            "added_at": int(time.time()),
            "meeting_id": meeting_id,
            "debate_id": debate_id
        }
        
        if "points_entries" not in data:
            data["points_entries"] = []
        data["points_entries"].append(points_entry)
        save_data(data)
        
        return True
    except Exception as e:
        print(f"Error adding automatic points: {e}")
        return False

def award_meeting_attendance_points(meeting):
    """Award points to all members who attended a meeting"""
    try:
        participants = meeting.get("participants", [])
        meeting_id = meeting.get("id")
        
        for participant in participants:
            if participant.get("present", False):
                member_email = participant.get("email", "").strip().lower()
                if member_email:
                    add_automatic_points(
                        member_email=member_email,
                        criteria="meeting_attendance",
                        reason=f"Attended meeting: {meeting.get('title', 'QA Meeting')}",
                        meeting_id=meeting_id
                    )
        return True
    except Exception as e:
        print(f"Error awarding meeting attendance points: {e}")
        return False

def award_presentation_points(meeting):
    """Award points to members who presented in agenda items"""
    try:
        agenda = meeting.get("agenda", [])
        meeting_id = meeting.get("id")
        
        for agenda_item in agenda:
            owner_email = agenda_item.get("ownerEmail", "").strip().lower()
            if owner_email:
                # Check if this member was present at the meeting
                participants = meeting.get("participants", [])
                was_present = False
                for participant in participants:
                    if participant.get("email", "").strip().lower() == owner_email:
                        was_present = participant.get("present", False)
                        break
                
                if was_present:
                    add_automatic_points(
                        member_email=owner_email,
                        criteria="presentation",
                        reason=f"Presented: {agenda_item.get('title', 'Agenda item')} in {meeting.get('title', 'QA Meeting')}",
                        meeting_id=meeting_id
                    )
        return True
    except Exception as e:
        print(f"Error awarding presentation points: {e}")
        return False

def award_debate_points(debate):
    """Award points to debate participants and winners
    
    Rules:
    - Winners keep badge but get NO points (no participation points, no winner points)
    - Non-winning participants get participation points
    - Judges/jury get participation points
    """
    try:
        debate_id = debate.get("id")
        teams = debate.get("teams", [])
        
        # First, identify winning teams (only when finished)
        winning_team_ids = set()
        if debate.get("status") == "finished":
            scores = debate.get("scores", {})
            jury_scores = scores.get("jury", {})
            public_scores = scores.get("public", {})
            
            # Calculate team totals
            team_totals = {}
            for team in teams:
                team_id = team.get("id")
                team_totals[team_id] = 0.0
                
                # Add jury scores
                for step_scores in jury_scores.values():
                    for judge_scores in step_scores.values():
                        if team_id in judge_scores:
                            if "default" in judge_scores[team_id]:
                                team_totals[team_id] += float(judge_scores[team_id]["default"])
                            else:
                                for score in judge_scores[team_id].values():
                                    team_totals[team_id] += float(score)
                
                # Add public scores (1 point per step won)
                for step_scores in public_scores.values():
                    if team_id in step_scores:
                        team_totals[team_id] += float(step_scores[team_id])
            
            # Find winning team(s)
            if team_totals:
                max_score = max(team_totals.values())
                winning_team_ids = set(team_id for team_id, score in team_totals.items() if score == max_score)
        
        # Collect all winning team member emails (these get NO points, just badge)
        winning_member_emails = set()
        for team in teams:
            if team.get("id") in winning_team_ids:
                members = team.get("members", [])
                for member_email in members:
                    if member_email:
                        winning_member_emails.add(member_email.strip().lower())
        
        # Award participation points ONLY to non-winning team members
        for team in teams:
            members = team.get("members", [])
            for member_email in members:
                if member_email:
                    email_lower = member_email.strip().lower()
                    # Skip winners - they get no points, just badge
                    if email_lower not in winning_member_emails:
                        add_automatic_points(
                            member_email=email_lower,
                            criteria="debate_participant",
                            reason=f"Participated in debate: {debate.get('affirmation', 'QA Debate')}",
                            debate_id=debate_id
                        )
        
        # Award participation points to judges/jury
        judges = debate.get("judges", [])
        for judge_email in judges:
            if judge_email:
                add_automatic_points(
                    member_email=judge_email.strip().lower(),
                    criteria="debate_participant",
                    reason=f"Jury member in debate: {debate.get('affirmation', 'QA Debate')}",
                    debate_id=debate_id
                )
        
        # Award badge to winners (but with 0 points - they already got prize)
        if debate.get("status") == "finished" and winning_team_ids:
            for team in teams:
                if team.get("id") in winning_team_ids:
                    members = team.get("members", [])
                    for member_email in members:
                        if member_email:
                            email_lower = member_email.strip().lower()
                            # Create entry with 0 points to preserve badge, but no point accumulation
                            try:
                                data = load_data()
                                points_entries = data.get("points_entries", [])
                                # Check if badge entry already exists
                                existing = next((e for e in points_entries 
                                               if e.get("member_email") == email_lower 
                                               and e.get("criteria") == "debate_winner" 
                                               and e.get("debate_id") == debate_id), None)
                                if not existing:
                                    points_entry = {
                                        "id": int(time.time() * 1000),
                                        "member_email": email_lower,
                                        "points": 0,  # 0 points - badge only
                                        "reason": f"Won debate: {debate.get('affirmation', 'QA Debate')} (badge only, prize already awarded)",
                                        "criteria": "debate_winner",
                                        "added_by": "system",
                                        "added_at": int(time.time()),
                                        "debate_id": debate_id
                                    }
                                    points_entries.append(points_entry)
                                    data["points_entries"] = points_entries
                                    save_data(data)
                            except Exception as e:
                                print(f"Error awarding winner badge: {e}")
        
        return True
    except Exception as e:
        print(f"Error awarding debate points: {e}")
        return False

@app.route("/api/rewards/points", methods=["GET", "POST"])
def rewards_points():
    try:
        data = load_data()
        if request.method == "POST":
            payload = request.json or {}
            member_email = (payload.get("member_email") or "").strip().lower()
            points = int(payload.get("points", 0))
            reason = (payload.get("reason") or "").strip()
            criteria = (payload.get("criteria") or "").strip()
            
            if not member_email or not reason:
                return jsonify({"error": "member_email and reason required"}), 400
            
            # Check if member exists
            member = _member_by_email(data, member_email)
            if not member:
                return jsonify({"error": "Member not found"}), 404
            
            # Add points entry
            points_entry = {
                "id": int(time.time() * 1000),
                "member_email": member_email,
                "points": points,
                "reason": reason,
                "criteria": criteria,
                "added_by": "admin",  # Could be extended to track who added
                "added_at": int(time.time())
            }
            
            if "points_entries" not in data:
                data["points_entries"] = []
            data["points_entries"].append(points_entry)
            save_data(data)
            
            return jsonify({"status": "added", "entry": points_entry}), 200
        
        # GET - return all points entries
        return jsonify(data.get("points_entries", []))
    except Exception as e:
        print("ERROR /api/rewards/points:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/rewards/leaderboard", methods=["GET"])
def rewards_leaderboard():
    try:
        data = load_data()
        members = data.get("members", [])
        points_entries = data.get("points_entries", [])
        
        # Calculate total points per member (excluding clan leads, external members, and inactive members)
        member_points = {}
        for member in members:
            # Skip members marked as clan lead
            if member.get("clan_lead", False):
                continue
            # Skip external members
            if member.get("external", False):
                continue
            # Skip inactive members
            member_status = (member.get("status") or "active").lower()
            if member_status in ("inactive", "inactive/maternity"):
                continue
                
            email = (member.get("email") or "").strip().lower()
            member_points[email] = {
                "name": member.get("name", ""),
                "email": email,
                "studio": member.get("studio", ""),
                "status": member.get("status", "active"),
                "total_points": 0,
                "points_breakdown": {},
                "recent_entries": []
            }
        
        # Sum up points from entries
        for entry in points_entries:
            email = (entry.get("member_email") or "").strip().lower()
            if email in member_points:
                points = int(entry.get("points", 0))
                criteria = entry.get("criteria", "manual")
                
                member_points[email]["total_points"] += points
                
                if criteria not in member_points[email]["points_breakdown"]:
                    member_points[email]["points_breakdown"][criteria] = 0
                member_points[email]["points_breakdown"][criteria] += points
                
                # Keep recent entries (last 10, but always include all debate_winner entries for badge display)
                member_points[email]["recent_entries"].append({
                    "points": points,
                    "reason": entry.get("reason", ""),
                    "criteria": criteria,
                    "added_at": entry.get("added_at", 0)
                })
        
        # Sort recent entries by date and limit, but preserve all debate_winner entries
        for email in member_points:
            all_entries = member_points[email]["recent_entries"]
            # Separate debate_winner entries from others
            debate_winner_entries = [e for e in all_entries if e.get("criteria") == "debate_winner"]
            other_entries = [e for e in all_entries if e.get("criteria") != "debate_winner"]
            
            # Sort and limit other entries (last 10)
            other_entries.sort(key=lambda x: x["added_at"], reverse=True)
            other_entries = other_entries[:10]
            
            # Sort debate_winner entries by date
            debate_winner_entries.sort(key=lambda x: x["added_at"], reverse=True)
            
            # Combine: debate_winner entries first (all of them), then other recent entries
            member_points[email]["recent_entries"] = debate_winner_entries + other_entries
        
        # Convert to list and sort by total points
        leaderboard = list(member_points.values())
        leaderboard.sort(key=lambda x: x["total_points"], reverse=True)
        
        return jsonify(leaderboard)
    except Exception as e:
        print("ERROR /api/rewards/leaderboard:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/rewards/criteria", methods=["GET", "POST"])
def rewards_criteria():
    try:
        data = load_data()
        if request.method == "POST":
            payload = request.json or {}
            name = (payload.get("name") or "").strip()
            points = int(payload.get("points", 0))
            description = (payload.get("description") or "").strip()
            
            if not name or points == 0:
                return jsonify({"error": "name and points required"}), 400
            
            criteria = {
                "id": int(time.time() * 1000),
                "name": name,
                "points": points,
                "description": description,
                "created_at": int(time.time())
            }
            
            if "points_criteria" not in data:
                data["points_criteria"] = []
            data["points_criteria"].append(criteria)
            save_data(data)
            
            return jsonify({"status": "added", "criteria": criteria}), 200
        
        # GET - return all criteria
        return jsonify(data.get("points_criteria", []))
    except Exception as e:
        print("ERROR /api/rewards/criteria:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/rewards/criteria/<int:criteria_id>", methods=["DELETE"])
def delete_criteria(criteria_id):
    try:
        data = load_data()
        criteria_list = data.get("points_criteria", [])
        
        # Find and remove criteria
        for i, criteria in enumerate(criteria_list):
            if criteria.get("id") == criteria_id:
                removed = criteria_list.pop(i)
                data["points_criteria"] = criteria_list
                save_data(data)
                return jsonify({"status": "deleted", "removed": removed}), 200
        
        return jsonify({"error": "Criteria not found"}), 404
    except Exception as e:
        print("ERROR /api/rewards/criteria/<id>:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/rewards/points/<int:entry_id>", methods=["DELETE"])
def delete_points_entry(entry_id):
    try:
        data = load_data()
        points_entries = data.get("points_entries", [])
        
        # Find and remove entry
        for i, entry in enumerate(points_entries):
            if entry.get("id") == entry_id:
                removed = points_entries.pop(i)
                data["points_entries"] = points_entries
                save_data(data)
                return jsonify({"status": "deleted", "removed": removed}), 200
        
        return jsonify({"error": "Entry not found"}), 404
    except Exception as e:
        print("ERROR /api/rewards/points/<id>:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/rewards/award-retroactive", methods=["POST"])
def award_retroactive_points():
    """Award points for all past meetings and debates"""
    try:
        data = load_data()
        meetings = data.get("meetings", [])
        debates = data.get("debates", [])
        
        awarded_meetings = 0
        awarded_debates = 0
        
        # Award points for all completed meetings
        for meeting in meetings:
            if isFinished(meeting):
                if award_meeting_attendance_points(meeting):
                    awarded_meetings += 1
                # Also award presentation points
                award_presentation_points(meeting)
        
        # Award points for all finished debates
        for debate in debates:
            if debate.get("status") == "finished":
                if award_debate_points(debate):
                    awarded_debates += 1
        
        return jsonify({
            "status": "completed",
            "awarded_meetings": awarded_meetings,
            "awarded_debates": awarded_debates,
            "message": f"Awarded points for {awarded_meetings} meetings and {awarded_debates} debates"
        })
    except Exception as e:
        print("ERROR /api/rewards/award-retroactive:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/rewards/recalculate-points", methods=["POST"])
def recalculate_all_points():
    """Reset and recalculate all automatic points (meeting attendance, presentations, debates)"""
    try:
        # Create explicit backup before recalculating
        backup_name = f"{DATA_FILE}.before_recalculate.{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if os.path.exists(DATA_FILE):
            shutil.copy2(DATA_FILE, backup_name)
            print(f"Created backup before recalculate: {backup_name}")
        
        data = load_data()
        
        # Validate data structure before proceeding
        if not isinstance(data, dict):
            raise ValueError("Invalid data structure")
        
        # Verify critical data exists
        if "members" not in data or "meetings" not in data:
            raise ValueError("Critical data missing - aborting recalculate to prevent data loss")
        
        points_entries = data.get("points_entries", [])
        meetings = data.get("meetings", [])
        debates = data.get("debates", [])
        
        # Remove all automatic points entries (system-awarded, not manual)
        automatic_criteria = ("meeting_attendance", "presentation", "debate_participant", "debate_winner")
        automatic_entries = [e for e in points_entries 
                            if e.get("criteria") in automatic_criteria 
                            and e.get("added_by") == "system"]
        
        remaining_entries = [e for e in points_entries 
                            if e not in automatic_entries]
        
        data["points_entries"] = remaining_entries
        save_data(data)
        
        # Re-award points for all finished meetings
        recalculated_meetings = 0
        recalculated_presentations = 0
        for meeting in meetings:
            if isFinished(meeting):
                if award_meeting_attendance_points(meeting):
                    recalculated_meetings += 1
                if award_presentation_points(meeting):
                    recalculated_presentations += 1
        
        # Re-award points for all finished debates using new rules
        recalculated_debates = 0
        for debate in debates:
            if debate.get("status") == "finished":
                if award_debate_points(debate):
                    recalculated_debates += 1
        
        return jsonify({
            "status": "completed",
            "removed_entries": len(automatic_entries),
            "recalculated_meetings": recalculated_meetings,
            "recalculated_presentations": recalculated_presentations,
            "recalculated_debates": recalculated_debates,
            "message": f"Reset {len(automatic_entries)} automatic points entries. Recalculated: {recalculated_meetings} meetings, {recalculated_presentations} presentations, {recalculated_debates} debates"
        })
    except Exception as e:
        print("ERROR /api/rewards/recalculate-points:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/rewards/cleanup-orphaned", methods=["POST"])
def cleanup_orphaned_points():
    """Remove points entries for deleted meetings and debates"""
    try:
        data = load_data()
        meetings = data.get("meetings", [])
        debates = data.get("debates", [])
        points_entries = data.get("points_entries", [])
        
        # Get valid meeting and debate IDs
        valid_meeting_ids = {str(m.get("id")) for m in meetings}
        valid_debate_ids = {str(d.get("id")) for d in debates}
        
        # Count orphaned entries
        orphaned_count = 0
        cleaned_entries = []
        
        for entry in points_entries:
            meeting_id = str(entry.get("meeting_id", ""))
            debate_id = str(entry.get("debate_id", ""))
            
            # Keep entry if it has a valid meeting or debate ID, or if it's manual (no meeting/debate ID)
            if (meeting_id and meeting_id in valid_meeting_ids) or \
               (debate_id and debate_id in valid_debate_ids) or \
               (not meeting_id and not debate_id):
                cleaned_entries.append(entry)
            else:
                orphaned_count += 1
        
        # Update the data
        data["points_entries"] = cleaned_entries
        save_data(data)
        
        return jsonify({
            "status": "completed",
            "orphaned_removed": orphaned_count,
            "remaining_entries": len(cleaned_entries),
            "message": f"Removed {orphaned_count} orphaned points entries"
        })
    except Exception as e:
        print("ERROR /api/rewards/cleanup-orphaned:", e)
        return jsonify({"error": str(e)}), 500

def isFinished(meeting):
    """Check if meeting is finished (date has passed)"""
    try:
        meeting_date = meeting.get("date", "")
        if not meeting_date:
            return False
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        return meeting_date < today
    except:
        return False

# ==========================================
# ========== FEEDBACK FORMS (nou) ==========
# ==========================================

# Optional: Teams Incoming Webhook for one-click send
TEAMS_WEBHOOK_URL = os.getenv("TEAMS_WEBHOOK_URL", "")

@app.route("/api/feedback/forms", methods=["GET", "POST", "PUT", "DELETE"])
def feedback_forms():
    try:
        data = load_data()
        if request.method == "POST":
            p = request.json or {}
            mid = p.get("meeting_id")
            title = (p.get("title") or "").strip()
            desc = (p.get("description") or "").strip()
            questions = p.get("questions") or []
            if not mid or not title or not isinstance(questions, list) or not questions:
                return jsonify({"error": "meeting_id, title, questions obligatorii"}), 400
            if not _meeting_by_id(data, mid):
                return jsonify({"error": "Meeting not found"}), 404
            fid = int(time.time() * 1000)
            form = {
                "id": fid,
                "meeting_id": mid,
                "title": title,
                "description": desc,
                "questions": questions,   # [{id,type,text,options?,required?}]
                "responses": {},          # email -> {ts, answers:{qid: value|[values]}}
                "created_at": int(time.time()),
                "qr": None,
            }
            data["feedback_forms"].append(form)
            save_data(data)
            return jsonify({"status": "saved", "id": fid}), 200

        if request.method == "PUT":
            p = request.json or {}
            fid = p.get("id")
            if not fid:
                return jsonify({"error": "Missing id"}), 400
            fs = data.get("feedback_forms", [])
            for i, f in enumerate(fs):
                if str(f.get("id")) == str(fid):
                    if f.get("responses"):
                        p.pop("meeting_id", None)  # don't change meeting after responses
                    for k in ("title", "description", "questions"):
                        if k in p:
                            fs[i][k] = p[k]
                    data["feedback_forms"] = fs
                    save_data(data)
                    return jsonify({"status": "updated"}), 200

        if request.method == "DELETE":
            fid = request.args.get("id")
            if not fid:
                return jsonify({"error": "Missing id"}), 400
            fs = [f for f in data.get("feedback_forms", []) if str(f.get("id")) != str(fid)]
            data["feedback_forms"] = fs
            save_data(data)
            return jsonify({"status": "deleted"}), 200

        # GET
        mid = request.args.get("meeting_id")
        fs = data.get("feedback_forms", [])
        if mid:
            fs = [f for f in fs if str(f.get("meeting_id")) == str(mid)]
        # —— compat: propagate qr_url/form_url to top level for UI —
        out = []
        for f in fs:
            f2 = dict(f)
            if isinstance(f2.get("qr"), dict):
                f2["qr_url"] = f2["qr"].get("qr_url")
                f2["form_url"] = f2["qr"].get("url")
            out.append(f2)
        return jsonify(out)
    except Exception as e:
        print("ERROR /api/feedback/forms:", e)
        return jsonify({"error": str(e)}), 500

# QR pentru feedback form
@app.route("/api/feedback/forms/<fid>/qr", methods=["POST"])
def feedback_qr(fid):
    try:
        data = load_data()
        fs = data.get("feedback_forms", [])
        form = next((f for f in fs if str(f.get("id")) == str(fid)), None)
        if not form:
                            return jsonify({"error": "Form not found"}), 404
        url = url_for("feedback_fill", fid=fid, _external=True)
        qr_url, ts = _versioned_qr_png(url, f"qr_fb_{fid}")
        form["qr"] = {"url": url, "qr_url": qr_url, "ts": ts}
        for i, f in enumerate(fs):
            if str(f.get("id")) == str(fid):
                fs[i] = form
                break
        data["feedback_forms"] = fs
        save_data(data)
        # —— compat: include form_url alias for frontend —
        return jsonify({"qr_url": qr_url, "url": url, "form_url": url, "ts": ts})
    except Exception as e:
        print("ERROR /api/feedback/forms/<fid>/qr:", e)
        return jsonify({"error": str(e)}), 500

# helper: build AI feedback message (avoid logic duplication)
def _build_feedback_ai_message(form, extra_suggestions=""):
    data = load_data()
    mt = _meeting_by_id(data, form.get("meeting_id")) or {}
    url = form.get("qr", {}).get("url") or url_for("feedback_fill", fid=form.get("id"), _external=True)
    title = mt.get("title", "QA Meeting")
    date = mt.get("date", "")
    topic = mt.get("topic", "")
    agenda = mt.get("agenda", [])
    
    # Build agenda context
    agenda_context = ""
    if agenda:
        agenda_items = [f"- {a.get('start', '')}-{a.get('end', '')}: {a.get('title', '')}" for a in agenda if a.get('title')]
        agenda_context = "\n".join(agenda_items)
    
    system = (
        "You write short, warm internal messages asking colleagues to fill feedback. "
        "Do NOT use marketing-y CTA. Keep it 2-4 short lines. English language. "
        "Return ONLY the message content, no prefixes like 'Here is a message:' or similar."
    )
    
    prompt = f"""
Write a short message (2–4 lines) in English for Teams asking for feedback.
Meeting context: {title} ({date}) – {topic}
{f"Agenda covered: {agenda_context}" if agenda_context else ""}
Politely say we are waiting for feedback.
Include this link explicitly: {url}
Avoid emojis; collegial tone.
{f"Additional context: {extra_suggestions}" if extra_suggestions.strip() else ""}

Return ONLY the message text, no explanations or prefixes.
"""
    resp = _llm.chat.completions.create(
        model=LM_MODEL_ID,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        temperature=0.3,
    )
    text = (resp.choices[0].message.content or "").strip()
    return {"text": text, "message": text, "link": url, "qr_url": form.get("qr", {}).get("qr_url")}

# Copie AI pentru Teams (mesaj scurt, colegial)
@app.route("/api/feedback/forms/<fid>/ai-copy", methods=["POST"])
def feedback_ai_copy(fid):
    try:
        data = load_data()
        form = next((f for f in data.get("feedback_forms", []) if str(f.get("id")) == str(fid)), None)
        if not form:
            return jsonify({"error": "Form not found"}), 404
        
        payload = request.json or {}
        extra_suggestions = payload.get("extra_suggestions", "")
        out = _build_feedback_ai_message(form, extra_suggestions)
        return jsonify(out)
    except Exception as e:
        print("ERROR /api/feedback/forms/<fid>/ai-copy:", e)
        return jsonify({"error": str(e)}), 500

# —— ALIAS compat pentru frontend: /ai-teams (identic cu /ai-copy) —
@app.route("/api/feedback/forms/<fid>/ai-teams", methods=["POST"])
def feedback_ai_teams(fid):
    try:
        data = load_data()
        form = next((f for f in data.get("feedback_forms", []) if str(f.get("id")) == str(fid)), None)
        if not form:
            return jsonify({"error": "Form not found"}), 404
        
        payload = request.json or {}
        extra_suggestions = payload.get("extra_suggestions", "")
        out = _build_feedback_ai_message(form, extra_suggestions)
        return jsonify(out)
    except Exception as e:
        print("ERROR /api/feedback/forms/<fid>/ai-teams:", e)
        return jsonify({"error": str(e)}), 500

def _aggregate_feedback(form):
    qs = form.get("questions") or []
    resp = form.get("responses") or {}
    aggr = {"total_responses": len(resp), "questions": []}

    # responses are stored as { email: { ts, answers: {qid: value|[values]} } }
    for q in qs:
        qid = q.get("id")
        qtype = (q.get("type") or "text").lower()
        title = q.get("title") or ""
        entry = {"title": title, "type": qtype}

        if qtype in ("single", "multi"):
            opts = [str(o) for o in (q.get("options") or [])]
            counts = {o: 0 for o in opts}
            for r in resp.values():
                a = (r.get("answers") or {}).get(qid)
                if qtype == "single":
                    if a is not None:
                        s = str(a)
                        if s in counts:
                            counts[s] += 1
                else:
                    if isinstance(a, list):
                        for s in map(str, a):
                            if s in counts:
                                counts[s] += 1
            entry["options"] = [{"value": o, "count": counts[o]} for o in opts]

        elif qtype == "rating":
            total = 0.0
            cnt = 0
            dist = {}
            for r in resp.values():
                v = (r.get("answers") or {}).get(qid)
                try:
                    if v is None:
                        continue
                    fv = float(v)
                    total += fv
                    cnt += 1
                    key = str(int(round(fv)))
                    dist[key] = dist.get(key, 0) + 1
                except Exception:
                    pass
            entry["avg"] = (total / cnt) if cnt else None
            entry["counts"] = dist

        elif qtype == "rating_presenter":
            # For rating_presenter, answers is an object: { "presenter1": 4, "presenter2": 5 }
            presenters = q.get("presenters", [])
            presenter_ratings = {p: {"total": 0.0, "count": 0, "dist": {}} for p in presenters}
            
            for r in resp.values():
                v = (r.get("answers") or {}).get(qid)
                if isinstance(v, dict):
                    for presenter, rating in v.items():
                        if presenter in presenter_ratings:
                            try:
                                fv = float(rating)
                                presenter_ratings[presenter]["total"] += fv
                                presenter_ratings[presenter]["count"] += 1
                                key = str(int(round(fv)))
                                presenter_ratings[presenter]["dist"][key] = presenter_ratings[presenter]["dist"].get(key, 0) + 1
                            except Exception:
                                pass
            
            # Format presenter ratings
            entry["presenter_ratings"] = []
            for presenter in presenters:
                pr = presenter_ratings[presenter]
                entry["presenter_ratings"].append({
                    "presenter": presenter,
                    "avg": (pr["total"] / pr["count"]) if pr["count"] > 0 else None,
                    "count": pr["count"],
                    "counts": pr["dist"]
                })

        else:  # text
            texts = []
            for r in resp.values():
                v = (r.get("answers") or {}).get(qid)
                if isinstance(v, str) and v.strip():
                    texts.append(v.strip())
            entry["responses"] = texts

        aggr["questions"].append(entry)

    return aggr

# Get single feedback form by ID
@app.route("/api/feedback/forms/<fid>", methods=["GET"])
def get_feedback_form(fid):
    try:
        data = load_data()
        form = next((f for f in data.get("feedback_forms", []) if str(f.get("id")) == str(fid)), None)
        if not form:
            return jsonify({"error": "Form not found"}), 404
        
        # Get meeting data for context
        meeting = _meeting_by_id(data, form.get("meeting_id")) or {}
        form_with_meeting = dict(form)
        form_with_meeting["meeting_title"] = meeting.get("title", "")
        form_with_meeting["meeting_date"] = meeting.get("date", "")
        form_with_meeting["meeting_topic"] = meeting.get("topic", "")
        
        return jsonify(form_with_meeting)
    except Exception as e:
        print("ERROR /api/feedback/forms/<fid>:", e)
        return jsonify({"error": str(e)}), 500

# Rezultate agregate (pentru UI)
@app.route("/api/feedback/forms/<fid>/results", methods=["GET"])
def feedback_results(fid):
    try:
        data = load_data()
        form = next((f for f in data.get("feedback_forms", []) if str(f.get("id")) == str(fid)), None)
        if not form:
                            return jsonify({"error": "Form not found"}), 404
        return jsonify(_aggregate_feedback(form))
    except Exception as e:
        print("ERROR /api/feedback/forms/<fid>/results:", e)
        return jsonify({"error": str(e)}), 500

# Submit feedback responses
@app.route("/api/feedback/forms/<fid>/responses", methods=["POST"])
def feedback_responses(fid):
    try:
        data = load_data()
        form = next((f for f in data.get("feedback_forms", []) if str(f.get("id")) == str(fid)), None)
        if not form:
            return jsonify({"error": "Form not found"}), 404
        
        payload = request.json or {}
        email = payload.get("email", "").strip().lower()
        answers = payload.get("answers", {})
        
        if not email:
            return jsonify({"error": "Email required"}), 400
        
        # Check if email is invited to the meeting
        meeting = _meeting_by_id(data, form.get("meeting_id")) or {}
        invited_map = _participants_by_email_map(meeting)
        if email not in invited_map:
            return jsonify({"error": "Email is not in the invite list"}), 403
        
        # Store the response
        form.setdefault("responses", {})[email] = {
            "ts": int(time.time()),
            "answers": answers
        }
        
        # Persist the data
        for i, f in enumerate(data.get("feedback_forms", [])):
            if str(f.get("id")) == str(fid):
                data["feedback_forms"][i] = form
                break
        save_data(data)
        
        return jsonify({"status": "ok"})
    except Exception as e:
        print("ERROR /api/feedback/forms/<fid>/responses:", e)
        return jsonify({"error": str(e)}), 500

# Send message to Teams via Incoming Webhook (optional, one-click)
@app.route("/api/feedback/forms/<fid>/teams-send", methods=["POST"])
def feedback_teams_send(fid):
    try:
        if not TEAMS_WEBHOOK_URL:
            return jsonify({"error": "Missing TEAMS_WEBHOOK_URL"}), 400
        data = load_data()
        form = next((f for f in data.get("feedback_forms", []) if str(f.get("id")) == str(fid)), None)
        if not form:
                            return jsonify({"error": "Form not found"}), 404
        msg = (request.json or {}).get("text") or f"Please complete the feedback: {url_for('feedback_fill', fid=fid, _external=True)}"
        import json as _json
        from urllib import request as _urlreq
        payload = _json.dumps({"text": msg}).encode("utf-8")
        req = _urlreq.Request(TEAMS_WEBHOOK_URL, data=payload, headers={"Content-Type": "application/json"})
        with _urlreq.urlopen(req) as resp:
            _ = resp.read()
        return jsonify({"status": "sent"})
    except Exception as e:
        print("ERROR teams-send:", e)
        return jsonify({"error": str(e)}), 500

# ========== Public page: complete feedback ==========
@app.route("/feedback/<fid>", methods=["GET", "POST"])
@app.route("/feedback", methods=["GET", "POST"])
def feedback_fill(fid=None):
    try:
        # Handle both /feedback/<fid> and /feedback?id=<fid> formats
        if not fid:
            fid = request.args.get("id")
        
        if not fid:
            return make_response("Form ID required", 400)
            
        data = load_data()
        form = next((f for f in data.get("feedback_forms", []) if str(f.get("id")) == str(fid)), None)
        if not form:
            return make_response("Form not found", 404)
        meeting = _meeting_by_id(data, form.get("meeting_id")) or {}

        # Format dorit?
        def want_json():
            if (request.args.get("format") or "").lower() == "json":
                return True
            accept = (request.headers.get("accept") or "").lower()
            return "application/json" in accept

        # Who responds?
        email = ""
        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
        else:
            email = (request.args.get("email") or "").strip().lower()

        # POST: record response
        if request.method == "POST" and email:
            invited_map = _participants_by_email_map(meeting)
            if email not in invited_map:
                if want_json():
                    return jsonify({"error": "Email is not in the invite list"}), 403
                return render_template("feedback_fill.html", error="You are not in the invite list.", form=form, meeting=meeting, email="")
            answers = {}
            for q in form.get("questions", []):
                qid = q.get("id")
                qtype = (q.get("type") or "text").lower()
                if qtype == "multi":
                    answers[qid] = request.form.getlist(qid)
                else:
                    answers[qid] = request.form.get(qid)
            # single response per email (overwrite)
            form.setdefault("responses", {})[email] = {"ts": int(time.time()), "answers": answers}
            # persist
            for i, f in enumerate(data.get("feedback_forms", [])):
                if str(f.get("id")) == str(fid):
                    data["feedback_forms"][i] = form
                    break
            save_data(data)
            if want_json():
                return jsonify({"status": "ok"})
            return render_template("feedback_fill.html", done=True, form=form, meeting=meeting, email=email)

        # GET: request email or show form
        if not email:
            if want_json():
                return jsonify({
                    "form": form,
                    "meeting": {"id": meeting.get("id"), "title": meeting.get("title"), "date": meeting.get("date")}
                })
            return render_template("feedback_fill.html", form=form, meeting=meeting, email="")

        invited_map = _participants_by_email_map(meeting)
        if email not in invited_map:
            if want_json():
                return jsonify({"error": "Email is not in the invite list"}), 403
            return render_template("feedback_fill.html", error="You are not in the invite list.", form=form, meeting=meeting, email="")

        return render_template("feedback_fill.html", form=form, meeting=meeting, email=email)
    except Exception as e:
        print("ERROR /feedback/<fid>:", e)
        return make_response("Feedback error.", 500)

# ---------- PPTX ----------
@app.route("/api/pptx-report", methods=["POST"])
def pptx_report():
    try:
        payload = request.json or {}
        filename = generate_pptx_report(payload)
        return jsonify({"filename": filename})
    except Exception as e:
        print("ERROR /api/pptx-report:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/static/generated/<filename>")
def serve_generated_file(filename):
    """Serve generated files (PPTX, HTML reports)"""
    try:
        return send_from_directory("static/generated", filename)
    except Exception as e:
        print(f"ERROR serving generated file {filename}:", e)
        return jsonify({"error": "File not found"}), 404

# ---------- AI Reports ----------
@app.route("/api/ai/generate-report", methods=["POST"])
def generate_ai_report():
    try:
        payload = request.json or {}
        prompt = payload.get("prompt", "")
        period = payload.get("period", "")
        report_type = payload.get("type", "quarter")
        data = payload.get("data", {})
        
        # Use the existing AI function to generate the report
        from utils.gpt_utils import generate_ai_report_content
        report_content = generate_ai_report_content(prompt, data)
        
        return jsonify({
            "report": report_content,
            "period": period,
            "type": report_type,
            "status": "success"
        })
    except Exception as e:
        print("ERROR /api/ai/generate-report:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/generate-report-html", methods=["POST"])
def generate_report_html():
    try:
        payload = request.json or {}
        report = payload.get("report", {})
        filename = payload.get("filename", "report")
        
        # Avoid UnicodeEncodeError on Windows consoles by printing ASCII-safe preview
        try:
            print(f"Generating HTML for: {filename}")
            print("Report data:", ascii(report))
        except Exception:
            try:
                print(f"Generating HTML for: {filename}")
                print("Report data: <unavailable for console>")
            except Exception:
                pass
        
        # Generate HTML report
        html_content = generate_html_report(report)
        
        # Save HTML file
        import os
        import time
        
        generated_dir = "static/generated"
        os.makedirs(generated_dir, exist_ok=True)
        
        timestamp = int(time.time())
        html_filename = f"{filename}_{timestamp}.html"
        html_path = os.path.join(generated_dir, html_filename)
        
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        # Return download URL
        download_url = f"/static/generated/{html_filename}"
        return jsonify({
            "download_url": download_url,
            "filename": html_filename,
            "status": "success"
        })
    except Exception as e:
        print("ERROR /api/generate-report-html:", e)
        return jsonify({"error": str(e)}), 500

def generate_html_report(report):
    period = report.get('period', 'Unknown Period')
    content = report.get('content', 'No content available')
    data = report.get('data', {})
    report_type = report.get('type', 'quarter')
    settings = report.get('settings', {})
    
    # Clean up content for HTML
    html_content = content.replace('**', '<strong>').replace('**', '</strong>')
    html_content = html_content.replace('\n- ', '\n<li>').replace('\n', '<br>')
    html_content = html_content.replace('<li>', '<ul><li>').replace('</li><br>', '</li></ul><br>')
    
    html_template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>QA Leadership Report - {period}</title>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
                background: #f8fafc;
            }}
            .header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 40px;
                border-radius: 12px;
                text-align: center;
                margin-bottom: 30px;
                box-shadow: 0 8px 25px rgba(102, 126, 234, 0.3);
            }}
            .header h1 {{
                margin: 0 0 10px 0;
                font-size: 2.5em;
                font-weight: 700;
            }}
            .header p {{
                margin: 0;
                font-size: 1.2em;
                opacity: 0.9;
            }}
            .content {{
                background: white;
                padding: 40px;
                border-radius: 12px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                margin-bottom: 30px;
            }}
            .section {{
                margin-bottom: 30px;
                padding: 20px;
                border-left: 4px solid #3b82f6;
                background: #f8fafc;
                border-radius: 8px;
            }}
            .section h2 {{
                color: #1e40af;
                margin-top: 0;
                font-size: 1.5em;
                border-bottom: 2px solid #e5e7eb;
                padding-bottom: 10px;
            }}
            .stats {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin: 20px 0;
            }}
            .stat-card {{
                background: white;
                padding: 20px;
                border-radius: 8px;
                text-align: center;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                border: 1px solid #e5e7eb;
            }}
            .stat-number {{
                font-size: 2em;
                font-weight: 700;
                color: #3b82f6;
                margin-bottom: 5px;
            }}
            .stat-label {{
                color: #6b7280;
                font-size: 0.9em;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            ul {{
                padding-left: 20px;
            }}
            li {{
                margin-bottom: 8px;
            }}
            .footer {{
                text-align: center;
                color: #6b7280;
                font-size: 0.9em;
                margin-top: 40px;
                padding: 20px;
                border-top: 1px solid #e5e7eb;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>QA Leadership Report</h1>
            <p>{period} - {report_type.title()} Analysis</p>
        </div>
        
        <div class="content">
            <div class="stats">
                <div class="stat-card">
                    <div class="stat-number">{data.get('totalMeetings', 0)}</div>
                    <div class="stat-label">Total Meetings</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{data.get('averageAttendance', 0):.1f}%</div>
                    <div class="stat-label">Avg Attendance</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{data.get('averageRating', 0):.1f}/5</div>
                    <div class="stat-label">Avg Rating</div>
                </div>
            </div>
            
            <div class="section">
                <h2>Report Content</h2>
                <div>{html_content}</div>
            </div>
        </div>
        
        <div class="footer">
            <p>Generated on {time.strftime('%Y-%m-%d %H:%M:%S')} | QA Leadership Tool</p>
        </div>
    </body>
    </html>
    """
    
    return html_template

@app.route("/api/rewards/badges", methods=["GET", "POST"])
def rewards_badges():
    try:
        data = load_data()
        if request.method == "POST":
            payload = request.json or {}
            icon = (payload.get("icon") or "").strip()
            name = (payload.get("name") or "").strip()
            points = int(payload.get("points", 0))
            category = (payload.get("category") or "monthly").strip()
            
            if not icon or not name:
                return jsonify({"error": "icon and name required"}), 400
            
            badge = {
                "id": int(time.time() * 1000),
                "icon": icon,
                "name": name,
                "points": points,
                "category": category,
                "created_at": int(time.time())
            }
            
            if "custom_badges" not in data:
                data["custom_badges"] = []
            data["custom_badges"].append(badge)
            save_data(data)
            
            return jsonify({"status": "added", "badge": badge}), 200
        
        # GET - return all custom badges
        return jsonify(data.get("custom_badges", []))
    except Exception as e:
        print("ERROR /api/rewards/badges:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/rewards/badges/<int:badge_id>", methods=["DELETE"])
def delete_custom_badge(badge_id):
    try:
        data = load_data()
        badges_list = data.get("custom_badges", [])
        
        # Find and remove badge
        for i, badge in enumerate(badges_list):
            if badge.get("id") == badge_id:
                removed = badges_list.pop(i)
                data["custom_badges"] = badges_list
                save_data(data)
                return jsonify({"status": "deleted", "removed": removed}), 200
        
        return jsonify({"error": "Badge not found"}), 404
    except Exception as e:
        print("ERROR DELETE /api/rewards/badges/<id>:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/quizz")
def quizz_page():
    return render_template("quizz.html")

# ---------- Quiz Sessions (Live) ----------
@app.route("/api/quiz-sessions", methods=["GET", "POST", "PUT", "DELETE"])
def quiz_sessions():
    try:
        data = load_data()
        data.setdefault("quiz_sessions", [])
        if request.method == "POST":
            p = request.json or {}
            sid = int(time.time() * 1000)
            session = {
                "id": sid,
                "quiz_id": p.get("quiz_id"),
                "meeting_id": p.get("meeting_id"),
                "status": "waiting",  # waiting|running|reveal|finished
                "phase": "waiting",  # waiting|question|leaderboard
                "current_index": -1,
                "reveal": False,
                "players": {},  # pid -> {nickname, score}
                "answers": {},  # qidx -> {pid -> {answer, time_ms, correct}}
                "created_at": int(time.time() * 1000)
            }
            data["quiz_sessions"].append(session)
            save_data(data)
            return jsonify({"status": "created", "id": sid}), 200
        if request.method == "PUT":
            p = request.json or {}
            sid = p.get("id")
            if not sid:
                return jsonify({"error": "Missing id"}), 400
            sessions = data.get("quiz_sessions", [])
            found = None
            for i, s in enumerate(sessions):
                if str(s.get("id")) == str(sid):
                    found = i
                    break
            if found is None:
                return jsonify({"error": "Not found"}), 404
            # allowed updates
            for k, v in p.items():
                if k == "id":
                    continue
                sessions[found][k] = v
            data["quiz_sessions"] = sessions
            save_data(data)
            return jsonify({"status": "updated"}), 200
        if request.method == "DELETE":
            sid = request.args.get("id")
            if not sid:
                return jsonify({"error": "Missing id"}), 400
            data["quiz_sessions"] = [s for s in data.get("quiz_sessions", []) if str(s.get("id")) != str(sid)]
            save_data(data)
            return jsonify({"status": "deleted"}), 200
        # GET
        return jsonify(data.get("quiz_sessions", []))
    except Exception as e:
        print("ERROR /api/quiz-sessions:", e)
        return jsonify({"error": str(e)}), 500

# Generate QR for player join
@app.route("/api/quiz-sessions/<sid>/qr", methods=["POST"])
def quiz_session_qr(sid):
    try:
        data = load_data()
        sessions = data.get("quiz_sessions", [])
        sess = next((s for s in sessions if str(s.get("id")) == str(sid)), None)
        if not sess:
            return jsonify({"error": "Session not found"}), 404
        join_url = url_for("quiz_join", sid=sid, _external=True)
        qr_url, ts = _versioned_qr_png(join_url, f"qr_quiz_{sid}")
        sess["join_qr"] = {"url": join_url, "qr_url": qr_url, "ts": ts}
        for i, s in enumerate(sessions):
            if str(s.get("id")) == str(sid):
                sessions[i] = sess
                break
        data["quiz_sessions"] = sessions
        save_data(data)
        return jsonify({"qr_url": qr_url, "join_url": join_url, "ts": ts})
    except Exception as e:
        print("ERROR /api/quiz-sessions/<sid>/qr:", e)
        return jsonify({"error": str(e)}), 500

# Player join page
@app.route("/quiz/<sid>/join", methods=["GET", "POST"])
def quiz_join(sid):
    try:
        data = load_data()
        sessions = data.get("quiz_sessions", [])
        sess = next((s for s in sessions if str(s.get("id")) == str(sid)), None)
        if not sess:
            return make_response("Session not found", 404)
        if request.method == "POST":
            nickname = (request.form.get("nickname") or "").strip()
            if not nickname:
                return make_response("Nickname required", 400)
            pid = str(int(time.time() * 1000))
            players = sess.get("players") or {}
            players[pid] = {"nickname": nickname, "score": 0}
            sess["players"] = players
            for i, s in enumerate(sessions):
                if str(s.get("id")) == str(sid):
                    sessions[i] = sess
                    break
            data["quiz_sessions"] = sessions
            save_data(data)
            # redirect into play page with pid stored via URL param
            return redirect(url_for("quiz_play", sid=sid, pid=pid))
        # render join page
        return render_template("quiz_join.html", sid=str(sid))
    except Exception as e:
        print("ERROR /quiz/<sid>/join:", e)
        return make_response("Error", 500)

# Player play page
@app.route("/quiz/<sid>/play")
def quiz_play(sid):
    try:
        return render_template("quiz_play.html", sid=str(sid), pid=request.args.get("pid", ""))
    except Exception as e:
        print("ERROR /quiz/<sid>/play:", e)
        return make_response("Error", 500)

# Admin controls: start/next/reveal/end
@app.route("/api/quiz-sessions/<sid>/control", methods=["POST"])
def quiz_control(sid):
    try:
        data = load_data()
        sessions = data.get("quiz_sessions", [])
        sess = next((s for s in sessions if str(s.get("id")) == str(sid)), None)
        if not sess:
            return jsonify({"error": "Session not found"}), 404
        payload = request.json or {}
        action = (payload.get("action") or "").lower()
        quiz = next((q for q in data.get("quizzes", []) if str(q.get("id")) == str(sess.get("quiz_id"))), None)
        total_q = len((quiz or {}).get("questions", []))
        now_ms = int(time.time() * 1000)
        if action == "start":
            sess["status"] = "running"
            sess["current_index"] = 0 if total_q > 0 else -1
            sess["reveal"] = False
            sess["phase"] = "question"
            sess["q_started_at"] = now_ms
        elif action == "next":
            # toggle between question -> leaderboard -> next question
            phase = sess.get("phase", "question")
            if phase == "question":
                sess["phase"] = "leaderboard"
                sess["reveal"] = True
                sess["status"] = "reveal"
            else:
                ci = int(sess.get("current_index", -1)) + 1
                if ci < total_q:
                    sess["current_index"] = ci
                    sess["reveal"] = False
                    sess["status"] = "running"
                    sess["phase"] = "question"
                    sess["q_started_at"] = now_ms
                    (sess.setdefault("answers", {}))[str(ci)] = {}
                else:
                    sess["status"] = "finished"
                    sess["phase"] = "leaderboard"
        elif action == "reveal":
            sess["reveal"] = True
            sess["status"] = "reveal"
            sess["phase"] = "leaderboard"
        elif action == "end":
            sess["status"] = "finished"
        else:
            return jsonify({"error": "Unknown action"}), 400
        for i, s in enumerate(sessions):
            if str(s.get("id")) == str(sid):
                sessions[i] = sess
                break
        data["quiz_sessions"] = sessions
        save_data(data)
        return jsonify({"status": "ok"})
    except Exception as e:
        print("ERROR /api/quiz-sessions/<sid>/control:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/quiz-sessions/<sid>/state", methods=["GET"])
def quiz_state(sid):
    try:
        data = load_data()
        sess = next((s for s in data.get("quiz_sessions", []) if str(s.get("id")) == str(sid)), None)
        if not sess:
            return jsonify({"error": "Session not found"}), 404
        quiz = next((q for q in data.get("quizzes", []) if str(q.get("id")) == str(sess.get("quiz_id"))), None)
        current_index = int(sess.get("current_index", -1))
        reveal = bool(sess.get("reveal", False))
        questions = quiz.get("questions", []) if quiz else []
        # time left uses per-question time if provided
        qobj = questions[current_index] if (0 <= current_index < len(questions)) else None
        time_per_q = int((qobj or {}).get("time_sec") or (quiz or {}).get("time_per_question", 30))
        q_started_at = int(sess.get("q_started_at")) if sess.get("q_started_at") else None
        now_ms = int(time.time() * 1000)
        time_left = None
        if q_started_at and time_per_q > 0 and current_index >= 0:
            time_left = max(0, (q_started_at + time_per_q * 1000) - now_ms)
        payload = {
            "status": sess.get("status"),
            "phase": sess.get("phase", "question"),
            "current_index": current_index,
            "reveal": reveal,
            "players": sess.get("players", {}),
            "leaderboard": _compute_quiz_leaderboard(sess),
            "question": None,
            "time_left_ms": time_left,
            "time_total_sec": time_per_q,
        }
        if 0 <= current_index < len(questions):
            q = dict(questions[current_index])
            if not reveal:
                q.pop("correct", None)
                q.pop("order", None)
                q.pop("map", None)
            payload["question"] = q
        return jsonify(payload)
    except Exception as e:
        print("ERROR /api/quiz-sessions/<sid>/state:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/quiz-sessions/<sid>/submit", methods=["POST"])
def quiz_submit(sid):
    try:
        data = load_data()
        sessions = data.get("quiz_sessions", [])
        sess = next((s for s in sessions if str(s.get("id")) == str(sid)), None)
        if not sess:
            return jsonify({"error": "Session not found"}), 404
        p = request.json or {}
        pid = str(p.get("pid") or "")
        if pid not in (sess.get("players") or {}):
            return jsonify({"error": "Player not in session"}), 403
        quiz = next((q for q in data.get("quizzes", []) if str(q.get("id")) == str(sess.get("quiz_id"))), None)
        ci = int(sess.get("current_index", -1))
        if ci < 0:
            return jsonify({"error": "No active question"}), 400
        question = (quiz or {}).get("questions", [])[ci] if quiz else None
        if not question:
            return jsonify({"error": "Question not found"}), 404
        # record
        now_ms = int(time.time() * 1000)
        ans_map = (sess.setdefault("answers", {})).setdefault(str(ci), {})
        if pid in ans_map:
            return jsonify({"error": "Already answered"}), 400
        submitted = {
            "answer": p.get("answer"),
            "ts": now_ms
        }
        # grade to get correctness ratio in [0..1]
        correctness_ratio = _grade_quiz_ratio(question, p.get("answer"))
        # compute time ratio using per-question time
        time_per_q = int((question or {}).get("time_sec") or (quiz or {}).get("time_per_question", 30))
        q_started_at = int(sess.get("q_started_at")) if sess.get("q_started_at") else None
        time_ratio = 1.0
        if q_started_at and time_per_q > 0:
            elapsed = max(0, now_ms - q_started_at)
            remaining = max(0, time_per_q * 1000 - elapsed)
            time_ratio = (remaining / (time_per_q * 1000))
        points_max = float((question or {}).get("points") or 1)
        points_earned = points_max * correctness_ratio * time_ratio
        # optional penalty for completely wrong answers
        penalty = 0.0
        if (p.get("penalize_wrong") and correctness_ratio == 0.0):
            penalty = -float((question or {}).get("penalty_points") or 0.5)
        total_delta = max(0.0, points_earned + penalty) if not p.get("penalize_wrong") else (points_earned + penalty)
        submitted["correct"] = (correctness_ratio == 1.0)
        submitted["points"] = round(total_delta,3)
        ans_map[pid] = submitted
        # update player score
        player = sess["players"].get(pid, {"nickname": "", "score": 0})
        player["score"] = round(float(player.get("score", 0)) + submitted["points"], 3)
        sess["players"][pid] = player
        # persist
        for i, s in enumerate(sessions):
            if str(s.get("id")) == str(sid):
                sessions[i] = sess
                break
        data["quiz_sessions"] = sessions
        save_data(data)
        return jsonify({"status": "recorded", "points": submitted["points"], "time_ratio": round(time_ratio,3), "correctness_ratio": round(correctness_ratio,3)})
    except Exception as e:
        print("ERROR /api/quiz-sessions/<sid>/submit:", e)
        return jsonify({"error": str(e)}), 500

def _grade_quiz_ratio(question: dict, answer_payload) -> float:
    qtype = (question.get("type") or "single").lower()
    if qtype == "single":
        return 1.0 if str(answer_payload) == str(question.get("correct")) else 0.0
    if qtype == "multiple":
        try:
            sub = set(map(str, answer_payload or []))
            corr = set(map(str, (question.get("correct") or [])))
            return 1.0 if sub == corr else 0.0
        except Exception:
            return 0.0
    if qtype == "order":
        correct_order = list(map(str, question.get("order") or []))
        sub = list(map(str, answer_payload or []))
        if not correct_order or not sub:
            return 0.0
        max_len = min(len(correct_order), len(sub))
        matched = 0
        for i in range(max_len):
            if sub[i] == correct_order[i]:
                matched += 1
            else:
                break
        return matched/len(correct_order) if len(correct_order)>0 else 0.0
    if qtype == "match":
        corr = question.get("map") or {}
        sub = answer_payload or {}
        if not isinstance(sub, dict):
            return 0.0
        keys = set(map(int, corr.keys() if hasattr(corr, 'keys') else [])) | set(map(int, sub.keys() if hasattr(sub, 'keys') else []))
        if not keys:
            return 0.0
        correct_pairs = 0
        for k in keys:
            if str(sub.get(k)) == str(corr.get(k)):
                correct_pairs += 1
        return correct_pairs/len(keys)
    return 0.0

def _compute_quiz_leaderboard(sess: dict):
    players = sess.get("players") or {}
    lb = [{"pid": pid, "nickname": p.get("nickname"), "score": float(p.get("score", 0))} for pid, p in players.items()]
    lb.sort(key=lambda x: (-x["score"], x["nickname"] or ""))
    return lb

if __name__ == "__main__":
    ensure_data_file()
    app.run(debug=True)
