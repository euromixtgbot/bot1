#!/usr/bin/env python3
"""
Перевірка останніх записів в Google Sheets
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from google_sheets_service import _sheet

def check_last_records():
    """Перевіряє останні записи в таблиці"""
    print("=== ПЕРЕВІРКА ОСТАННІХ ЗАПИСІВ ===\n")
    
    try:
        all_values = _sheet.get_all_values()
        print(f"Всього рядків: {len(all_values)}")
        
        # Показуємо заголовки
        headers = all_values[0] if all_values else []
        print(f"Заголовки: {headers}")
        
        # Показуємо останні 3 записи
        print(f"\nОстанні 3 записи:")
        for i, row in enumerate(all_values[-3:], start=len(all_values)-2):
            print(f"Рядок {i}: {row}")
            
    except Exception as e:
        print(f"Помилка: {e}")

if __name__ == "__main__":
    check_last_records()
