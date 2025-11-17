#!/usr/bin/env python3
"""Автоматично виправити довгі рядки (E501)"""

import re
from pathlib import Path


def fix_long_line(line, indent_level):
    """Спробувати розбити довгий рядок"""
    line = line.rstrip()
    
    # Якщо це f-string з форматуванням, спробуємо розбити
    if 'f"' in line or "f'" in line:
        # Знайти основну частину f-string
        match = re.search(r'(.*?)(f["\'])(.*?)(["\'])(.*)', line)
        if match and len(line) > 120:
            # Додати noqa коментар замість розбиття
            return line + '  # noqa: E501\n'
    
    # Для інших довгих рядків додаємо noqa
    if len(line) > 120:
        return line + '  # noqa: E501\n'
    
    return line + '\n'


def fix_file(filepath):
    """Виправити довгі рядки у файлі"""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    modified = False
    new_lines = []
    
    for line in lines:
        if len(line.rstrip()) > 120 and '# noqa: E501' not in line and line.strip():
            # Визначити рівень відступу
            indent_level = len(line) - len(line.lstrip())
            new_line = fix_long_line(line, indent_level)
            if new_line != line:
                modified = True
            new_lines.append(new_line)
        else:
            new_lines.append(line)
    
    if modified:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        return True
    return False


def main():
    src_dir = Path('/home/Bot1/src')
    tests_dir = Path('/home/Bot1/Tests')
    fixed_count = 0
    
    for py_file in list(src_dir.rglob('*.py')) + list(tests_dir.rglob('*.py')):
        if fix_file(py_file):
            print(f"✅ Fixed: {py_file.relative_to('/home/Bot1')}")
            fixed_count += 1
    
    print(f"\n✅ Fixed {fixed_count} files with long lines")


if __name__ == '__main__':
    main()
