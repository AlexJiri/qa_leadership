import json
import shutil
from datetime import datetime

# Shadow Copy 18 - has TestCon meeting + most complete (42 members, 223 points entries)
shadow_file = r'\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy18\AlexJ\cursorProject\qa_leadership_tool_final\data.json'
target_file = 'data.json'

print("Restoring Shadow Copy 18 (TestCon + most complete)...")

try:
    with open(shadow_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    meetings = [m.get('title', '') for m in data.get('meetings', [])]
    
    print(f"\nShadow Copy 18 contains:")
    print(f"  Members: {len(data.get('members', []))}")
    print(f"  Meetings: {len(meetings)}")
    print(f"  Feedback forms: {len(data.get('feedback_forms', []))}")
    print(f"  Points entries: {len(data.get('points_entries', []))}")
    print(f"\n  Meetings list:")
    for i, m in enumerate(meetings, 1):
        print(f"    {i}. {m}")
    
    has_testcon = any('TestCon' in m for m in meetings)
    print(f"\n  TestCon meeting present: {has_testcon}")
    
    if has_testcon:
        # Backup current
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup = f"data.json.before_shadow18.{timestamp}"
        shutil.copy2(target_file, backup)
        print(f"\nBacked up current: {backup}")
        
        # Restore
        with open(target_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"✓ RESTORED Shadow Copy 18!")
        print("\nPlease restart Flask application!")
    else:
        print("\n✗ TestCon meeting not found in this shadow copy")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

