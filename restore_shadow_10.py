import json
import shutil
from datetime import datetime

# Shadow Copy 10 - has 9 meetings (vs 8 in Shadow Copy 18)
shadow_file = r'\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy10\AlexJ\cursorProject\qa_leadership_tool_final\data.json'
target_file = 'data.json'

print("Restoring Shadow Copy 10 (9 meetings)...")

try:
    with open(shadow_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"\nShadow Copy 10 contains:")
    print(f"  Members: {len(data.get('members', []))}")
    print(f"  Meetings: {len(data.get('meetings', []))}")
    print(f"  Feedback forms: {len(data.get('feedback_forms', []))}")
    print(f"  Points entries: {len(data.get('points_entries', []))}")
    print(f"  Total points: {sum(e.get('points', 0) for e in data.get('points_entries', []))}")
    
    # Backup current
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = f"data.json.before_shadow10.{timestamp}"
    shutil.copy2(target_file, backup)
    print(f"\nBacked up current: {backup}")
    
    # Restore
    with open(target_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✓ RESTORED Shadow Copy 10!")
    print("\nPlease restart Flask application!")
    
except Exception as e:
    print(f"Error: {e}")

