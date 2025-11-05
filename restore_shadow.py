import shutil
import json

shadow_file = r'\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy10\AlexJ\cursorProject\qa_leadership_tool_final\data.json'
target_file = 'data.json'

print("Restoring from shadow copy...")
print(f"Source: {shadow_file}")

# Read from shadow copy and write to target
with open(shadow_file, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Verify data
print(f"\nData contains:")
print(f"  Members: {len(data.get('members', []))}")
print(f"  Meetings: {len(data.get('meetings', []))}")
print(f"  Feedback forms: {len(data.get('feedback_forms', []))}")
print(f"  Points entries: {len(data.get('points_entries', []))}")

# Write to target
with open(target_file, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"\n✓ RESTORED data.json!")
print("Please restart your Flask application!")

