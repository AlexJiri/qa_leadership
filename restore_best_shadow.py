import json
import shutil
from datetime import datetime

# Shadow copy 18 - seems most complete (42 members, 223 points)
shadow_file = r'\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy18\AlexJ\cursorProject\qa_leadership_tool_final\data.json'
target_file = 'data.json'

print("Restoring from BEST shadow copy (ShadowCopy18)...")
print(f"Source: {shadow_file}")

try:
    # Read from shadow copy
    with open(shadow_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Verify data
    print(f"\nData contains:")
    print(f"  Members: {len(data.get('members', []))}")
    print(f"  Meetings: {len(data.get('meetings', []))}")
    print(f"  Feedback forms: {len(data.get('feedback_forms', []))}")
    print(f"  Points entries: {len(data.get('points_entries', []))}")
    print(f"  Debates: {len(data.get('debates', []))}")
    
    # Calculate total points
    total_points = sum(entry.get('points', 0) for entry in data.get('points_entries', []))
    print(f"  Total points: {total_points}")
    
    # Backup current
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_current = f"data.json.before_best_restore.{timestamp}"
    shutil.copy2(target_file, backup_current)
    print(f"\nBacked up current: {backup_current}")
    
    # Write to target
    with open(target_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ RESTORED data.json from BEST shadow copy!")
    print("Please restart your Flask application!")
    
except Exception as e:
    print(f"Error: {e}")
    print("\nTrying alternative shadow copy...")
    
    # Try shadow copy 19 (second best)
    shadow_file_alt = r'\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy19\AlexJ\cursorProject\qa_leadership_tool_final\data.json'
    try:
        with open(shadow_file_alt, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"\nAlternative data contains:")
        print(f"  Members: {len(data.get('members', []))}")
        print(f"  Meetings: {len(data.get('meetings', []))}")
        print(f"  Feedback forms: {len(data.get('feedback_forms', []))}")
        print(f"  Points entries: {len(data.get('points_entries', []))}")
        
        with open(target_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"\n✓ RESTORED from alternative shadow copy!")
    except Exception as e2:
        print(f"Alternative also failed: {e2}")

