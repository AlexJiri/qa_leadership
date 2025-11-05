#!/usr/bin/env python3
"""
Find shadow copy that contains "TestCon - brief overview" meeting
"""
import os
import json

def check_shadow_file(shadow_path, target_file):
    """Check if file exists in shadow"""
    drive = target_file[0]
    rest = target_file[3:]
    shadow_file = f"{shadow_path}\\{rest}"
    
    if not os.path.exists(shadow_file):
        return None
    
    try:
        with open(shadow_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Check for TestCon meeting
        meetings = data.get('meetings', [])
        testcon_meetings = [m for m in meetings if 'TestCon' in m.get('title', '') or 'testcon' in m.get('title', '').lower()]
        
        return {
            'file': shadow_file,
            'data': data,
            'meetings': meetings,
            'testcon_meetings': testcon_meetings,
            'members': len(data.get('members', [])),
            'feedback_forms': len(data.get('feedback_forms', [])),
            'points_entries': len(data.get('points_entries', []))
        }
    except Exception as e:
        return {'error': str(e)}

def main():
    target_file = r"C:\AlexJ\cursorProject\qa_leadership_tool_final\data.json"
    
    print("=" * 80)
    print("SEARCHING FOR 'TestCon - brief overview' MEETING")
    print("=" * 80)
    print()
    
    found_shadows = []
    
    # Check all shadow copies
    for i in range(1, 20):
        shadow_path = f"\\\\?\\GLOBALROOT\\Device\\HarddiskVolumeShadowCopy{i}"
        print(f"Checking Shadow Copy {i}...", end=' ')
        
        result = check_shadow_file(shadow_path, target_file)
        
        if result and 'error' not in result:
            if result['testcon_meetings']:
                print(f"✓ FOUND TestCon meeting!")
                print(f"   Meetings: {len(result['meetings'])}")
                print(f"   Members: {result['members']}")
                print(f"   Feedback forms: {result['feedback_forms']}")
                print(f"   Points entries: {result['points_entries']}")
                print(f"   TestCon meetings found: {len(result['testcon_meetings'])}")
                for tm in result['testcon_meetings']:
                    print(f"      - {tm.get('title', 'Unknown')} (ID: {tm.get('id', 'Unknown')})")
                found_shadows.append({
                    'index': i,
                    'result': result
                })
            else:
                print(f"✗ No TestCon meeting (has {len(result['meetings'])} meetings)")
        elif result and 'error' in result:
            print(f"✗ Error: {result['error']}")
        else:
            print(f"✗ File not found")
    
    print()
    print("=" * 80)
    
    if found_shadows:
        print(f"Found {len(found_shadows)} shadow copy/copies with TestCon meeting:")
        print()
        for fs in found_shadows:
            print(f"Shadow Copy {fs['index']}:")
            print(f"  Meetings: {len(fs['result']['meetings'])}")
            print(f"  Members: {fs['result']['members']}")
            print(f"  Feedback forms: {fs['result']['feedback_forms']}")
            print(f"  Points entries: {fs['result']['points_entries']}")
            print()
        
        # Use the first/best one
        best = found_shadows[0]
        print(f"Restoring Shadow Copy {best['index']}...")
        
        import shutil
        from datetime import datetime
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup = f"data.json.before_testcon_restore.{timestamp}"
        shutil.copy2('data.json', backup)
        print(f"Backed up current: {backup}")
        
        with open('data.json', 'w', encoding='utf-8') as f:
            json.dump(best['result']['data'], f, ensure_ascii=False, indent=2)
        
        print(f"✓ RESTORED Shadow Copy {best['index']}!")
        print(f"  Meetings: {len(best['result']['meetings'])}")
        print(f"  Members: {best['result']['members']}")
        print(f"  Feedback forms: {len(best['result']['data'].get('feedback_forms', []))}")
        print(f"  Points entries: {len(best['result']['data'].get('points_entries', []))}")
        print("\nPlease restart Flask application!")
    else:
        print("✗ No shadow copy found with 'TestCon - brief overview' meeting")
        print("\nTrying to find any meeting with 'TestCon' in title...")
        
        # Check all shadows for any TestCon mention
        for i in range(1, 20):
            shadow_path = f"\\\\?\\GLOBALROOT\\Device\\HarddiskVolumeShadowCopy{i}"
            result = check_shadow_file(shadow_path, target_file)
            if result and 'error' not in result:
                meetings = result['meetings']
                for m in meetings:
                    title = m.get('title', '').lower()
                    if 'testcon' in title or 'test' in title:
                        print(f"\nShadow Copy {i} has meeting: '{m.get('title', 'Unknown')}'")
                        print(f"  Date: {m.get('date', 'Unknown')}")
                        print(f"  Total meetings in this shadow: {len(meetings)}")

if __name__ == "__main__":
    main()

