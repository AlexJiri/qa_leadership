#!/usr/bin/env python3
"""
Find shadow copy from yesterday (November 3, 2025)
"""
import os
import json
import subprocess
from datetime import datetime, timedelta

def get_shadow_copies_with_dates():
    """Get shadow copies with creation dates"""
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
                current_shadow['time_str'] = time_str
                # Parse date: 10/31/2025 10:13:24 PM
                try:
                    dt = datetime.strptime(time_str, '%m/%d/%Y %I:%M:%S %p')
                    current_shadow['datetime'] = dt
                    current_shadow['date'] = dt.date()
                except:
                    pass
        
        if current_shadow:
            shadows.append(current_shadow)
        
        return shadows
    except Exception as e:
        print(f"Error: {e}")
        return []

def try_access_shadow_file(shadow_path, file_path):
    """Try to access a file from shadow copy"""
    drive = file_path[0]
    rest = file_path[3:]
    shadow_file = f"{shadow_path}\\{rest}"
    if os.path.exists(shadow_file):
        return shadow_file
    return None

def analyze_file(filepath):
    """Analyze a JSON file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return {
            'members': len(data.get('members', [])),
            'meetings': len(data.get('meetings', [])),
            'feedback_forms': len(data.get('feedback_forms', [])),
            'points_entries': len(data.get('points_entries', [])),
            'debates': len(data.get('debates', [])),
            'quizzes': len(data.get('quizzes', [])),
            'size': os.path.getsize(filepath)
        }
    except:
        return None

def main():
    print("=" * 70)
    print("FINDING YESTERDAY'S SHADOW COPY (November 3, 2025)")
    print("=" * 70)
    print()
    
    target_file = r"C:\AlexJ\cursorProject\qa_leadership_tool_final\data.json"
    yesterday = datetime(2025, 11, 3).date()
    today = datetime(2025, 11, 4).date()
    
    shadows = get_shadow_copies_with_dates()
    print(f"Found {len(shadows)} shadow copies")
    print()
    
    # Sort by date (newest first)
    shadows.sort(key=lambda x: x.get('datetime', datetime.min), reverse=True)
    
    print("Checking shadow copies near yesterday...")
    print("-" * 70)
    
    found_files = []
    for i, shadow in enumerate(shadows, 1):
        shadow_date = shadow.get('date')
        shadow_dt = shadow.get('datetime')
        time_str = shadow.get('time_str', 'Unknown')
        
        if shadow_date:
            days_diff = (today - shadow_date).days
            print(f"\n{i}. {time_str} ({(today - shadow_date).days} days ago)")
        else:
            print(f"\n{i}. {time_str}")
        
        shadow_file = try_access_shadow_file(shadow['path'], target_file)
        if shadow_file and os.path.exists(shadow_file):
            stats = analyze_file(shadow_file)
            if stats:
                print(f"   ✓ Found! Size: {stats['size']:,} bytes")
                print(f"   Members: {stats['members']}, Meetings: {stats['meetings']}, "
                      f"Feedback: {stats['feedback_forms']}, Points: {stats['points_entries']}")
                
                score = (stats['members'] * 10 + stats['meetings'] * 50 + 
                        stats['feedback_forms'] * 30 + stats['points_entries'] * 5)
                
                found_files.append({
                    'shadow': shadow,
                    'file': shadow_file,
                    'stats': stats,
                    'score': score,
                    'days_diff': days_diff if shadow_date else 999
                })
                
                # If this is from yesterday or very close, highlight it
                if shadow_date == yesterday:
                    print(f"   ⭐ THIS IS FROM YESTERDAY!")
                elif shadow_date and abs((shadow_date - yesterday).days) <= 1:
                    print(f"   ⭐ Close to yesterday ({(yesterday - shadow_date).days} days difference)")
        else:
            print(f"   ✗ File not found")
    
    if found_files:
        # Find closest to yesterday
        closest = min(found_files, key=lambda x: abs(x['days_diff']))
        # Or find best overall if closest is too old
        best = max(found_files, key=lambda x: x['score'])
        
        print()
        print("=" * 70)
        print("CLOSEST TO YESTERDAY:")
        print("=" * 70)
        print(f"Date: {closest['shadow'].get('time_str', 'Unknown')}")
        print(f"Days from today: {closest['days_diff']}")
        print(f"File: {closest['file']}")
        print(f"Members: {closest['stats']['members']}")
        print(f"Meetings: {closest['stats']['meetings']}")
        print(f"Feedback forms: {closest['stats']['feedback_forms']}")
        print(f"Points entries: {closest['stats']['points_entries']}")
        print("=" * 70)
        print()
        
        print("=" * 70)
        print("BEST OVERALL (Most complete):")
        print("=" * 70)
        print(f"Date: {best['shadow'].get('time_str', 'Unknown')}")
        print(f"Days from today: {best['days_diff']}")
        print(f"File: {best['file']}")
        print(f"Members: {best['stats']['members']}")
        print(f"Meetings: {best['stats']['meetings']}")
        print(f"Feedback forms: {best['stats']['feedback_forms']}")
        print(f"Points entries: {best['stats']['points_entries']}")
        print("=" * 70)
        print()
        
        # Offer both options
        print("Options:")
        print("1. Restore CLOSEST to yesterday")
        print("2. Restore BEST OVERALL (most complete)")
        print("3. Cancel")
        
        choice = input("\nYour choice (1/2/3): ")
        
        if choice == '1':
            selected = closest
            print("\nRestoring CLOSEST to yesterday...")
        elif choice == '2':
            selected = best
            print("\nRestoring BEST OVERALL...")
        else:
            print("Cancelled.")
            return
        
        # Restore
        import shutil
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_current = f"data.json.before_restore.{timestamp}"
        shutil.copy2('data.json', backup_current)
        print(f"Backed up current: {backup_current}")
        
        # Read and write (to avoid same file error)
        with open(selected['file'], 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        with open('data.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"✓ RESTORED from: {selected['shadow'].get('time_str', 'Unknown')}")
        print("\nPlease restart Flask application!")
    else:
        print("\n✗ No valid files found in shadow copies")

if __name__ == "__main__":
    main()

