#!/usr/bin/env python3
"""
Перевірка заголовків Google Sheets
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from google_sheets_service import _sheet

def check_headers():
    """Перевіряє заголовки Google Sheets"""
    print("=== ПЕРЕВІРКА ЗАГОЛОВКІВ ===\n")
    
    # Отримуємо перший рядок повністю
    first_row = _sheet.row_values(1)
    print(f"Перший рядок (заголовки): {first_row}")
    print(f"Кількість заголовків: {len(first_row)}")
    
    for i, header in enumerate(first_row):
        print(f"  Колонка {i+1}: '{header}'")
    
    # Перевірка другого рядка для прикладу
    second_row = _sheet.row_values(2)
    print(f"\nДругий рядок (приклад): {second_row}")
    print(f"Кількість значень: {len(second_row)}")

if __name__ == "__main__":
    check_headers()
