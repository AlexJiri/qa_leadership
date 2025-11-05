#!/usr/bin/env python3
"""
Deep Recovery - Search for all possible data.json backups
"""
import os
import json
import shutil
from datetime import datetime

def find_all_data_files():
    """Find all data.json files in common locations"""
    locations = [
        r"C:\AlexJ",
        os.path.join(os.environ.get('USERPROFILE', ''), 'AppData', 'Local'),
        os.path.join(os.environ.get('USERPROFILE', ''), 'AppData', 'Roaming'),
        os.path.join(os.environ.get('USERPROFILE', ''), 'Documents'),
        os.path.join(os.environ.get('TEMP', '')),
        os.path.join(os.environ.get('TMP', '')),
    ]
    
    found_files = []
    
    for location in locations:
        if not os.path.exists(location):
            continue
        print(f"Searching {location}...")
        try:
            for root, dirs, files in os.walk(location):
                # Skip some directories
                skip_dirs = ['node_modules', '.git', '__pycache__', '.venv', 'venv']
                dirs[:] = [d for d in dirs if d not in skip_dirs]
                
                for file in files:
                    if 'data' in file.lower() and 'json' in file.lower():
                        full_path = os.path.join(root, file)
                        try:
                            size = os.path.getsize(full_path)
                            if size > 1000:  # At least 1KB
                                mtime = os.path.getmtime(full_path)
                                found_files.append({
                                    'path': full_path,
                                    'size': size,
                                    'mtime': mtime,
                                    'date': datetime.fromtimestamp(mtime)
                                })
                        except:
                            pass
        except Exception as e:
            print(f"  Error searching {location}: {e}")
    
    return found_files

def analyze_file(filepath):
    """Analyze a JSON file to see what it contains"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not isinstance(data, dict):
            return None
        
        stats = {
            'path': filepath,
            'size': os.path.getsize(filepath),
            'members': len(data.get('members', [])),
            'meetings': len(data.get('meetings', [])),
            'feedback_forms': len(data.get('feedback_forms', [])),
            'points_entries': len(data.get('points_entries', [])),
            'debates': len(data.get('debates', [])),
            'quizzes': len(data.get('quizzes', [])),
        }
        
        # Check if has points
        if stats['points_entries'] > 0:
            total_points = sum(entry.get('points', 0) for entry in data.get('points_entries', []))
            stats['total_points'] = total_points
        
        stats['score'] = (
            stats['members'] * 10 +
            stats['meetings'] * 50 +
            stats['feedback_forms'] * 30 +
            stats['points_entries'] * 5 +
            stats['debates'] * 20 +
            stats['quizzes'] * 20
        )
        
        return stats
    except Exception as e:
        return {'error': str(e)}

def main():
    print("=" * 70)
    print("DEEP DATA RECOVERY - Searching all locations")
    print("=" * 70)
    print()
    
    print("Searching for data.json files...")
    found_files = find_all_data_files()
    
    print(f"\nFound {len(found_files)} potential files")
    print()
    
    if not found_files:
        print("No files found. Trying alternative recovery methods...")
        return
    
    # Sort by modification time (newest first)
    found_files.sort(key=lambda x: x['mtime'], reverse=True)
    
    print("Analyzing files...")
    print("-" * 70)
    
    valid_files = []
    for f in found_files[:30]:  # Check top 30
        stats = analyze_file(f['path'])
        if stats and not stats.get('error'):
            valid_files.append(stats)
            print(f"\nFile: {os.path.basename(f['path'])}")
            print(f"  Path: {f['path']}")
            print(f"  Size: {stats['size']:,} bytes")
            print(f"  Members: {stats['members']}")
            print(f"  Meetings: {stats['meetings']}")
            print(f"  Feedback forms: {stats['feedback_forms']}")
            print(f"  Points entries: {stats['points_entries']}")
            if 'total_points' in stats:
                print(f"  Total points: {stats['total_points']}")
            print(f"  Score: {stats['score']}")
    
    if valid_files:
        # Find best file
        best = max(valid_files, key=lambda x: x['score'])
        
        print()
        print("=" * 70)
        print("BEST FILE FOUND:")
        print("=" * 70)
        print(f"Path: {best['path']}")
        print(f"Members: {best['members']}")
        print(f"Meetings: {best['meetings']}")
        print(f"Feedback forms: {best['feedback_forms']}")
        print(f"Points entries: {best['points_entries']}")
        print(f"Score: {best['score']}")
        print("=" * 70)
        print()
        
        response = input("Restore this file? (yes/no): ")
        if response.lower() == 'yes':
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_current = f"data.json.before_restore.{timestamp}"
            shutil.copy2('data.json', backup_current)
            print(f"Backed up current file: {backup_current}")
            
            shutil.copy2(best['path'], 'data.json')
            print(f"✓ RESTORED from: {best['path']}")
            print("\nPlease restart your Flask application!")
    else:
        print("\nNo valid data files found")

if __name__ == "__main__":
    main()

