#!/usr/bin/env python3
"""Видалити f prefix з strings без плейсхолдерів"""

import re
from pathlib import Path


def fix_f_strings(filepath):
    """Видалити f prefix з strings що не містять {} """
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    modified = False
    new_lines = []
    
    for line in lines:
        # Шукаємо f"..." або f'...' без {} всередині
        # Pattern for f-strings without placeholders
        patterns = [
            (r'(print\()f"([^"{}]*)"(\))', r'\1"\2"\3'),  # print(f"text")
            (r'(print\()f\'([^\'{}]*)\'(\))', r"\1'\2'\3"),  # print(f'text')
            (r'(\s+)f"([^"{}]*)"', r'\1"\2"'),  # f"text" with spaces
            (r'(\s+)f\'([^\'{}]*)\'', r"\1'\2'"),  # f'text' with spaces
        ]
        
        original = line
        for pattern, replacement in patterns:
            line = re.sub(pattern, replacement, line)
        
        if line != original:
            modified = True
        
        new_lines.append(line)
    
    if modified:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        return True
    return False


def main():
    # Знайти всі файли з F541
    import subprocess
    result = subprocess.run(
        ['/home/Bot1/venv/bin/flake8', 'Tests/', '--select=F541'],
        capture_output=True,
        text=True,
        cwd='/home/Bot1'
    )
    
    files_to_fix = set()
    for line in result.stdout.split('\n'):
        if line.strip():
            filepath = line.split(':')[0]
            files_to_fix.add(Path(filepath))
    
    fixed_count = 0
    for filepath in sorted(files_to_fix):
        if filepath.exists() and fix_f_strings(filepath):
            print(f"✅ Fixed: {filepath.name}")
            fixed_count += 1
    
    print(f"\n✅ Fixed {fixed_count} files")


if __name__ == '__main__':
    main()
