#!/usr/bin/env python3
"""
Emergency Data Recovery Script
Attempts to recover data.json from various sources
"""
import os
import json
import shutil
from datetime import datetime

DATA_FILE = "data.json"

def try_recover_from_backup():
    """Try to find backup files"""
    current_dir = os.path.dirname(os.path.abspath(DATA_FILE))
    backups = []
    
    # Check current directory
    for f in os.listdir(current_dir):
        if 'data' in f.lower() and 'json' in f.lower() and f != DATA_FILE:
            backups.append(os.path.join(current_dir, f))
    
    # Check parent directories
    parent = os.path.dirname(current_dir)
    if os.path.exists(parent):
        for root, dirs, files in os.walk(parent):
            for f in files:
                if 'data' in f.lower() and 'json' in f.lower() and f != DATA_FILE:
                    full_path = os.path.join(root, f)
                    try:
                        size = os.path.getsize(full_path)
                        if size > 100:  # More than just empty structure
                            backups.append(full_path)
                    except:
                        pass
    
    return backups

def try_recover_from_temp():
    """Check temp directories"""
    import tempfile
    temp_dirs = [
        tempfile.gettempdir(),
        os.path.join(os.environ.get('APPDATA', ''), 'Local', 'Temp'),
        os.path.join(os.environ.get('USERPROFILE', ''), 'AppData', 'Local', 'Temp')
    ]
    
    backups = []
    for temp_dir in temp_dirs:
        if os.path.exists(temp_dir):
            try:
                for root, dirs, files in os.walk(temp_dir):
                    for f in files:
                        if 'data' in f.lower() and 'json' in f.lower():
                            full_path = os.path.join(root, f)
                            try:
                                size = os.path.getsize(full_path)
                                if size > 100:
                                    backups.append(full_path)
                            except:
                                pass
            except:
                pass
    
    return backups

def analyze_file(filepath):
    """Analyze a file to see if it contains valid data"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not isinstance(data, dict):
            return None
        
        total_items = sum(len(v) if isinstance(v, list) else 1 for v in data.values())
        return {
            'path': filepath,
            'size': os.path.getsize(filepath),
            'total_items': total_items,
            'members': len(data.get('members', [])),
            'meetings': len(data.get('meetings', [])),
            'feedback_forms': len(data.get('feedback_forms', [])),
            'data': data
        }
    except Exception as e:
        return None

def main():
    print("=" * 60)
    print("EMERGENCY DATA RECOVERY")
    print("=" * 60)
    print()
    
    # Check current file
    print("1. Checking current data.json...")
    if os.path.exists(DATA_FILE):
        current = analyze_file(DATA_FILE)
        if current and current['total_items'] > 0:
            print(f"   ✓ Current file has {current['total_items']} items")
        else:
            print(f"   ✗ Current file is empty or corrupted")
    print()
    
    # Search for backups
    print("2. Searching for backup files...")
    backups = []
    backups.extend(try_recover_from_backup())
    backups.extend(try_recover_from_temp())
    
    if backups:
        print(f"   Found {len(backups)} potential backup files")
        print()
        print("3. Analyzing backup files...")
        valid_backups = []
        for backup in backups[:20]:  # Limit to first 20
            result = analyze_file(backup)
            if result and result['total_items'] > 0:
                valid_backups.append(result)
                print(f"   ✓ {os.path.basename(backup)}: {result['total_items']} items "
                      f"({result['members']} members, {result['meetings']} meetings)")
        
        if valid_backups:
            # Find the best backup (most items)
            best = max(valid_backups, key=lambda x: x['total_items'])
            print()
            print("=" * 60)
            print(f"BEST BACKUP FOUND: {best['path']}")
            print(f"  - Total items: {best['total_items']}")
            print(f"  - Members: {best['members']}")
            print(f"  - Meetings: {best['meetings']}")
            print(f"  - Feedback forms: {best['feedback_forms']}")
            print("=" * 60)
            print()
            
            response = input("Do you want to restore this backup? (yes/no): ")
            if response.lower() == 'yes':
                # Create backup of current (empty) file
                backup_current = f"{DATA_FILE}.empty.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                shutil.copy2(DATA_FILE, backup_current)
                print(f"   Created backup of current file: {backup_current}")
                
                # Restore from backup
                shutil.copy2(best['path'], DATA_FILE)
                print(f"   ✓ Restored data.json from {best['path']}")
                print()
                print("   RECOVERY COMPLETE! Please restart your application.")
                return True
    else:
        print("   ✗ No backup files found")
    
    print()
    print("=" * 60)
    print("RECOVERY FAILED - No valid backups found")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Check Windows File History (Right-click data.json → Properties → Previous Versions)")
    print("2. Check if you have any manual backups")
    print("3. Check email/cloud storage for exported data")
    print("4. Try data recovery software (Recuva, PhotoRec, etc.)")
    
    return False

if __name__ == "__main__":
    main()

