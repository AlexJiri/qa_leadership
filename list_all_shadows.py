#!/usr/bin/env python3
"""
List all shadow copies with full details and let user choose
"""
import os
import json
import subprocess
from datetime import datetime

def get_all_shadows():
    """Get all shadow copies with full info"""
    try:
        result = subprocess.run(['vssadmin', 'list', 'shadows'], 
                              capture_output=True, text=True, shell=True)
        
        shadows = []
        lines = result.stdout.split('\n')
        current = {}
        
        for line in lines:
            if 'Shadow Copy Volume:' in line:
                if current:
                    shadows.append(current)
                current = {
                    'path': line.split('Shadow Copy Volume:')[1].strip(),
                    'info': []
                }
            elif 'Creation time:' in line:
                current['time'] = line.split('Creation time:')[1].strip()
            elif current:
                current['info'].append(line.strip())
        
        if current:
            shadows.append(current)
        
        return shadows
    except Exception as e:
        print(f"Error: {e}")
        return []

def check_shadow_file(shadow_path, target_file):
    """Check if file exists in shadow and get stats"""
    drive = target_file[0]
    rest = target_file[3:]
    shadow_file = f"{shadow_path}\\{rest}"
    
    if not os.path.exists(shadow_file):
        return None
    
    try:
        size = os.path.getsize(shadow_file)
        with open(shadow_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return {
            'file': shadow_file,
            'size': size,
            'members': len(data.get('members', [])),
            'meetings': len(data.get('meetings', [])),
            'feedback_forms': len(data.get('feedback_forms', [])),
            'points_entries': len(data.get('points_entries', [])),
            'debates': len(data.get('debates', [])),
            'total_points': sum(e.get('points', 0) for e in data.get('points_entries', []))
        }
    except:
        return None

def main():
    target_file = r"C:\AlexJ\cursorProject\qa_leadership_tool_final\data.json"
    
    print("=" * 80)
    print("ALL AVAILABLE SHADOW COPIES")
    print("=" * 80)
    print()
    
    shadows = get_all_shadows()
    print(f"Found {len(shadows)} shadow copies\n")
    
    valid_shadows = []
    
    for i, shadow in enumerate(shadows, 1):
        time_str = shadow.get('time', 'Unknown')
        print(f"{i}. Shadow Copy {i} - {time_str}")
        
        stats = check_shadow_file(shadow['path'], target_file)
        if stats:
            print(f"   ✓ Valid file found!")
            print(f"   Size: {stats['size']:,} bytes")
            print(f"   Members: {stats['members']}")
            print(f"   Meetings: {stats['meetings']}")
            print(f"   Feedback forms: {stats['feedback_forms']}")
            print(f"   Points entries: {stats['points_entries']}")
            print(f"   Total points: {stats['total_points']}")
            print(f"   Debates: {stats['debates']}")
            
            score = (stats['members'] * 10 + stats['meetings'] * 50 + 
                    stats['feedback_forms'] * 30 + stats['points_entries'] * 5)
            print(f"   Score: {score}")
            
            valid_shadows.append({
                'index': i,
                'shadow': shadow,
                'stats': stats,
                'score': score
            })
        else:
            print(f"   ✗ File not found or invalid")
        print()
    
    if valid_shadows:
        # Sort by score
        valid_shadows.sort(key=lambda x: x['score'], reverse=True)
        
        print("=" * 80)
        print("SUMMARY - Best options:")
        print("=" * 80)
        for i, vs in enumerate(valid_shadows[:5], 1):
            print(f"{i}. Shadow Copy {vs['index']} - {vs['shadow'].get('time', 'Unknown')}")
            print(f"   Members: {vs['stats']['members']}, Meetings: {vs['stats']['meetings']}, "
                  f"Feedback: {vs['stats']['feedback_forms']}, Points: {vs['stats']['points_entries']}")
            print(f"   Total points: {vs['stats']['total_points']}, Score: {vs['score']}")
            print()
        
        print("=" * 80)
        choice = input(f"Enter shadow copy number to restore (1-{len(valid_shadows)}) or 'q' to quit: ")
        
        if choice.lower() != 'q':
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(valid_shadows):
                    selected = valid_shadows[idx]
                    
                    print(f"\nRestoring Shadow Copy {selected['index']}...")
                    
                    # Restore
                    import shutil
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    backup = f"data.json.before_shadow_{selected['index']}.{timestamp}"
                    shutil.copy2('data.json', backup)
                    print(f"Backed up current: {backup}")
                    
                    with open(selected['stats']['file'], 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    with open('data.json', 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    
                    print(f"✓ RESTORED!")
                    print(f"Date: {selected['shadow'].get('time', 'Unknown')}")
                    print(f"Members: {selected['stats']['members']}")
                    print(f"Meetings: {selected['stats']['meetings']}")
                    print(f"Feedback forms: {selected['stats']['feedback_forms']}")
                    print(f"Points entries: {selected['stats']['points_entries']}")
                    print(f"Total points: {selected['stats']['total_points']}")
                    print("\nPlease restart Flask application!")
                else:
                    print("Invalid choice")
            except ValueError:
                print("Invalid input")
    else:
        print("No valid shadow copies found")

if __name__ == "__main__":
    main()

