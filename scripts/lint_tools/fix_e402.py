#!/usr/bin/env python3
"""Fix E402 errors by adding noqa comments to imports after sys.path modifications"""

from pathlib import Path


def fix_file(filepath):
    """Add noqa: E402 to imports that come after sys.path.append"""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    modified = False
    found_syspath = False
    
    for i, line in enumerate(lines):
        # Detect sys.path.append or sys.path.insert
        if 'sys.path.' in line and ('append' in line or 'insert' in line):
            found_syspath = True
        
        # If we found sys.path modification and this is an import line
        if found_syspath and (line.strip().startswith('from ') or line.strip().startswith('import ')):
            # Check if noqa comment is already there
            if '# noqa: E402' not in line and line.strip() and not line.strip().startswith('#'):
                # Add the noqa comment before newline
                lines[i] = line.rstrip() + '  # noqa: E402\n'
                modified = True
    
    if modified:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        return True
    return False


def main():
    tests_dir = Path('/home/Bot1/Tests')
    fixed_count = 0
    
    for py_file in tests_dir.rglob('*.py'):
        if fix_file(py_file):
            print(f"✅ Fixed: {py_file.relative_to(tests_dir)}")
            fixed_count += 1
    
    print(f"\n✅ Fixed {fixed_count} files")


if __name__ == '__main__':
    main()
