#!/usr/bin/env python3
"""
Recover data.json from Windows Shadow Copies
"""
import os
import shutil
import subprocess
import json
from datetime import datetime

def get_shadow_copies():
    """Get list of shadow copies"""
    try:
        result = subprocess.run(['vssadmin', 'list', 'shadows'], 
                              capture_output=True, text=True, shell=True)
        shadows = []
        lines = result.stdout.split('\n')
        current_shadow = None
        
        for line in lines:
            if 'Shadow Copy Volume:' in line:
                shadow_path = line.split('Shadow Copy Volume:')[1].strip()
                if current_shadow:
                    shadows.append(current_shadow)
                current_shadow = {'path': shadow_path}
            elif 'Creation time:' in line and current_shadow:
                time_str = line.split('Creation time:')[1].strip()
                current_shadow['time'] = time_str
        
        if current_shadow:
            shadows.append(current_shadow)
        
        return shadows
    except Exception as e:
        print(f"Error getting shadow copies: {e}")
        return []

def try_access_shadow_file(shadow_path, file_path):
    """Try to access a file from shadow copy"""
    # Convert path to shadow copy format
    # Original: C:\AlexJ\cursorProject\qa_leadership_tool_final\data.json
    # Shadow: \\?\GLOBALROOT\Device\HarddiskVolumeShadowCopyX\...
    
    # Extract drive letter
    drive = file_path[0]  # C
    rest = file_path[3:]  # AlexJ\cursorProject\qa_leadership_tool_final\data.json
    
    shadow_file = f"{shadow_path}\\{rest}"
    
    if os.path.exists(shadow_file):
        return shadow_file
    return None

def main():
    print("=" * 70)
    print("RECOVERING FROM WINDOWS SHADOW COPIES")
    print("=" * 70)
    print()
    
    target_file = r"C:\AlexJ\cursorProject\qa_leadership_tool_final\data.json"
    
    shadows = get_shadow_copies()
    print(f"Found {len(shadows)} shadow copies")
    print()
    
    # Sort by time (newest first)
    shadows.sort(key=lambda x: x.get('time', ''), reverse=True)
    
    print("Checking shadow copies for data.json...")
    print("-" * 70)
    
    found_files = []
    for i, shadow in enumerate(shadows[:10], 1):  # Check top 10
        print(f"\n{i}. Shadow copy from: {shadow.get('time', 'Unknown')}")
        print(f"   Path: {shadow['path']}")
        
        shadow_file = try_access_shadow_file(shadow['path'], target_file)
        if shadow_file and os.path.exists(shadow_file):
            try:
                size = os.path.getsize(shadow_file)
                print(f"   ✓ Found file! Size: {size:,} bytes")
                
                # Try to read and validate
                with open(shadow_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                members = len(data.get('members', []))
                meetings = len(data.get('meetings', []))
                feedback = len(data.get('feedback_forms', []))
                points = len(data.get('points_entries', []))
                
                print(f"   Members: {members}, Meetings: {meetings}, Feedback: {feedback}, Points: {points}")
                
                score = members * 10 + meetings * 50 + feedback * 30 + points * 5
                found_files.append({
                    'shadow': shadow,
                    'file': shadow_file,
                    'size': size,
                    'members': members,
                    'meetings': meetings,
                    'feedback': feedback,
                    'points': points,
                    'score': score
                })
            except Exception as e:
                print(f"   ✗ Error reading: {e}")
        else:
            print(f"   ✗ File not found in this shadow copy")
    
    if found_files:
        # Find best file
        best = max(found_files, key=lambda x: x['score'])
        
        print()
        print("=" * 70)
        print("BEST RECOVERY OPTION:")
        print("=" * 70)
        print(f"Shadow Copy: {best['shadow'].get('time', 'Unknown')}")
        print(f"File: {best['file']}")
        print(f"Size: {best['size']:,} bytes")
        print(f"Members: {best['members']}")
        print(f"Meetings: {best['meetings']}")
        print(f"Feedback forms: {best['feedback']}")
        print(f"Points entries: {best['points']}")
        print("=" * 70)
        print()
        
        response = input("Restore this file? (yes/no): ")
        if response.lower() == 'yes':
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_current = f"data.json.before_shadow_restore.{timestamp}"
            shutil.copy2('data.json', backup_current)
            print(f"Backed up current: {backup_current}")
            
            shutil.copy2(best['file'], 'data.json')
            print(f"✓ RESTORED from shadow copy!")
            print("\nPlease restart Flask application!")
    else:
        print("\n✗ No valid files found in shadow copies")
        print("\nTry:")
        print("1. Right-click data.json → Properties → Previous Versions")
        print("2. Use Recuva or PhotoRec data recovery software")
        print("3. Check if you exported data to Excel or other files")

if __name__ == "__main__":
    main()

