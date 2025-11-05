#!/usr/bin/env python3
"""
Find shadow copy with updated "Automation in QA" feedback form
"""
import os
import json

def check_feedback_form(data):
    """Check if feedback form has the updated responses"""
    feedback_forms = data.get('feedback_forms', [])
    
    for form in feedback_forms:
        # Find "Automation in QA" form
        if 'Automation' in form.get('title', '') or 'automation' in form.get('title', '').lower():
            # Check if it has the meeting_id for "Automation in QA" meeting
            meeting_id = form.get('meeting_id', '')
            
            # Check responses - should have multiple responses with all questions answered
            responses = form.get('responses', {})
            
            # Count responses with complete answers (not just instructor rating)
            complete_responses = 0
            for email, response in responses.items():
                answers = response.get('answers', {})
                # Check if has multiple answers (not just q_4w9d2h9)
                if len(answers) > 1:
                    # Check for specific answers we added
                    if 'q_0icm77f' in answers or 'q_8yuqgat' in answers or 'q_xymybp3' in answers:
                        complete_responses += 1
            
            return {
                'form': form,
                'title': form.get('title', ''),
                'responses_count': len(responses),
                'complete_responses': complete_responses,
                'has_updated_data': complete_responses > 5  # We updated many responses
            }
    
    return None

def check_shadow_file(shadow_path, target_file):
    """Check shadow file for updated feedback"""
    drive = target_file[0]
    rest = target_file[3:]
    shadow_file = f"{shadow_path}\\{rest}"
    
    if not os.path.exists(shadow_file):
        return None
    
    try:
        with open(shadow_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        feedback_info = check_feedback_form(data)
        
        return {
            'file': shadow_file,
            'data': data,
            'feedback_info': feedback_info,
            'members': len(data.get('members', [])),
            'meetings': len(data.get('meetings', [])),
            'points_entries': len(data.get('points_entries', []))
        }
    except Exception as e:
        return {'error': str(e)}

def main():
    target_file = r"C:\AlexJ\cursorProject\qa_leadership_tool_final\data.json"
    
    print("=" * 80)
    print("SEARCHING FOR UPDATED 'Automation in QA' FEEDBACK FORM")
    print("=" * 80)
    print()
    
    found_shadows = []
    
    # Check all shadow copies
    for i in range(1, 20):
        shadow_path = f"\\\\?\\GLOBALROOT\\Device\\HarddiskVolumeShadowCopy{i}"
        print(f"Checking Shadow Copy {i}...", end=' ')
        
        result = check_shadow_file(shadow_path, target_file)
        
        if result and 'error' not in result:
            feedback_info = result.get('feedback_info')
            if feedback_info:
                print(f"✓ Found Automation feedback form!")
                print(f"   Form title: {feedback_info['title']}")
                print(f"   Total responses: {feedback_info['responses_count']}")
                print(f"   Complete responses: {feedback_info['complete_responses']}")
                print(f"   Has updated data: {feedback_info['has_updated_data']}")
                
                if feedback_info['has_updated_data']:
                    print(f"   ⭐ THIS HAS THE UPDATED DATA!")
                    found_shadows.append({
                        'index': i,
                        'result': result,
                        'feedback_info': feedback_info
                    })
            else:
                print(f"✗ No Automation feedback form found")
        elif result and 'error' in result:
            print(f"✗ Error: {result['error']}")
        else:
            print(f"✗ File not found")
    
    print()
    print("=" * 80)
    
    if found_shadows:
        print(f"Found {len(found_shadows)} shadow copy/copies with updated Automation feedback:")
        print()
        for fs in found_shadows:
            print(f"Shadow Copy {fs['index']}:")
            print(f"  Members: {fs['result']['members']}")
            print(f"  Meetings: {len(fs['result']['data'].get('meetings', []))}")
            print(f"  Feedback forms: {len(fs['result']['data'].get('feedback_forms', []))}")
            print(f"  Points entries: {fs['result']['points_entries']}")
            print(f"  Automation form responses: {fs['feedback_info']['responses_count']}")
            print(f"  Complete responses: {fs['feedback_info']['complete_responses']}")
            print()
        
        # Use the best one (most complete responses)
        best = max(found_shadows, key=lambda x: x['feedback_info']['complete_responses'])
        print(f"Restoring Shadow Copy {best['index']} (most complete)...")
        
        import shutil
        from datetime import datetime
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup = f"data.json.before_automation_restore.{timestamp}"
        shutil.copy2('data.json', backup)
        print(f"Backed up current: {backup}")
        
        with open('data.json', 'w', encoding='utf-8') as f:
            json.dump(best['result']['data'], f, ensure_ascii=False, indent=2)
        
        print(f"✓ RESTORED Shadow Copy {best['index']}!")
        print(f"  Members: {best['result']['members']}")
        print(f"  Meetings: {len(best['result']['data'].get('meetings', []))}")
        print(f"  Feedback forms: {len(best['result']['data'].get('feedback_forms', []))}")
        print(f"  Points entries: {best['result']['points_entries']}")
        print(f"  Automation form complete responses: {best['feedback_info']['complete_responses']}")
        print("\nPlease restart Flask application!")
    else:
        print("✗ No shadow copy found with updated Automation feedback form")
        print("\nChecking current data.json for Automation feedback...")
        
        # Check current file
        try:
            with open('data.json', 'r', encoding='utf-8') as f:
                current_data = json.load(f)
            
            current_feedback = check_feedback_form(current_data)
            if current_feedback:
                print(f"\nCurrent data.json has:")
                print(f"  Form title: {current_feedback['title']}")
                print(f"  Total responses: {current_feedback['responses_count']}")
                print(f"  Complete responses: {current_feedback['complete_responses']}")
                print(f"  Has updated data: {current_feedback['has_updated_data']}")
        except Exception as e:
            print(f"Error checking current file: {e}")

if __name__ == "__main__":
    main()

