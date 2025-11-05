import json
import shutil
from datetime import datetime

backup_file = r'C:\AlexJ\aitools\qa_leadership_tool_final\data.json'
current_file = 'data.json'

print("Checking backup file...")
try:
    with open(backup_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    members = len(data.get('members', []))
    meetings = len(data.get('meetings', []))
    feedback_forms = len(data.get('feedback_forms', []))
    points = len(data.get('points_entries', []))
    
    print(f"\nBackup file contains:")
    print(f"  - Members: {members}")
    print(f"  - Meetings: {meetings}")
    print(f"  - Feedback forms: {feedback_forms}")
    print(f"  - Points entries: {points}")
    
    if members > 0 or meetings > 0:
        print(f"\n✓ BACKUP CONTAINS DATA!")
        print(f"\nRestoring...")
        
        # Create backup of current empty file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        empty_backup = f"data.json.empty.{timestamp}"
        shutil.copy2(current_file, empty_backup)
        print(f"  - Saved current empty file as: {empty_backup}")
        
        # Restore from backup
        shutil.copy2(backup_file, current_file)
        print(f"  - ✓ RESTORED data.json from backup!")
        print(f"\n✓ RECOVERY COMPLETE!")
        print(f"\nPlease restart your Flask application to load the restored data.")
    else:
        print("\n✗ Backup file is also empty")
        
except Exception as e:
    print(f"Error: {e}")

