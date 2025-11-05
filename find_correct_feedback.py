#!/usr/bin/env python3
"""
Find shadow copy with correct "Automation in QA" feedback using q_4w9d2h9
"""
import os
import json

def check_feedback_form(data):
    """Check if feedback form has q_4w9d2h9 (rating_presenter)"""
    feedback_forms = data.get('feedback_forms', [])
    
    for form in feedback_forms:
        meeting_id = form.get('meeting_id', '')
        # "Automation in QA" meeting ID is "1759751298721"
        if meeting_id == "1759751298721":
            questions = form.get('questions', [])
            has_q4w9d2h9 = any(q.get('id') == 'q_4w9d2h9' for q in questions)
            
            if has_q4w9d2h9:
                responses = form.get('responses', {})
                # Count responses with q_4w9d2h9
                responses_with_q4w9d2h9 = sum(
                    1 for r in responses.values() 
                    if 'q_4w9d2h9' in r.get('answers', {})
                )
                
                # Count complete responses (with multiple answers)
                complete_responses = sum(
                    1 for r in responses.values()
                    if len(r.get('answers', {})) > 2  # More than just instructor rating
                )
                
                return {
                    'form': form,
                    'has_q4w9d2h9': True,
                    'responses_count': len(responses),
                    'responses_with_q4w9d2h9': responses_with_q4w9d2h9,
                    'complete_responses': complete_responses,
                    'has_updated_data': complete_responses >= 15  # We updated many responses
                }
    
    return None

def check_shadow_file(shadow_path, target_file):
    """Check shadow file"""
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
    print("SEARCHING FOR CORRECT 'Automation in QA' FEEDBACK (with q_4w9d2h9)")
    print("=" * 80)
    print()
    
    found_shadows = []
    
    # Check all shadow copies
    for i in range(1, 20):
        shadow_path = f"\\\\?\\GLOBALROOT\\Device\\HarddiskVolumeShadowCopy{i}"
        print(f"Shadow Copy {i}...", end=' ')
        
        result = check_shadow_file(shadow_path, target_file)
        
        if result and 'error' not in result:
            feedback_info = result.get('feedback_info')
            if feedback_info and feedback_info.get('has_q4w9d2h9'):
                print(f"✓ Found q_4w9d2h9!")
                print(f"   Responses: {feedback_info['responses_count']}")
                print(f"   With q_4w9d2h9: {feedback_info['responses_with_q4w9d2h9']}")
                print(f"   Complete: {feedback_info['complete_responses']}")
                
                if feedback_info['has_updated_data']:
                    print(f"   ⭐ HAS UPDATED DATA!")
                    found_shadows.append({
                        'index': i,
                        'result': result,
                        'feedback_info': feedback_info
                    })
            else:
                print(f"✗ No q_4w9d2h9 found")
        else:
            print(f"✗ Not found or error")
    
    print()
    print("=" * 80)
    
    if found_shadows:
        print(f"Found {len(found_shadows)} shadow copy/copies with correct feedback:")
        for fs in found_shadows:
            print(f"  Shadow Copy {fs['index']}: {fs['feedback_info']['complete_responses']} complete responses")
        
        # Use best one
        best = max(found_shadows, key=lambda x: x['feedback_info']['complete_responses'])
        print(f"\nRestoring Shadow Copy {best['index']}...")
        
        import shutil
        from datetime import datetime
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup = f"data.json.before_correct_feedback.{timestamp}"
        shutil.copy2('data.json', backup)
        print(f"Backed up current: {backup}")
        
        with open('data.json', 'w', encoding='utf-8') as f:
            json.dump(best['result']['data'], f, ensure_ascii=False, indent=2)
        
        print(f"✓ RESTORED!")
        print(f"  Complete responses: {best['feedback_info']['complete_responses']}")
        print(f"  Total responses: {best['feedback_info']['responses_count']}")
        print("\nPlease restart Flask application!")
    else:
        print("✗ No shadow copy found with q_4w9d2h9")
        print("\nThe updated feedback may have been lost.")
        print("You may need to re-enter the feedback data manually.")

if __name__ == "__main__":
    main()

