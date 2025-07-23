#!/usr/bin/env python3
"""
Видалення останнього тестового запису
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from google_sheets_service import _sheet

def remove_test_user():
    """Видаляє останній тестовий запис"""
    print("=== ВИДАЛЕННЯ ТЕСТОВОГО ЗАПИСУ ===\n")
    
    try:
        all_values = _sheet.get_all_values()
        total_rows = len(all_values)
        print(f"Всього рядків: {total_rows}")
        
        if total_rows > 1:
            last_row = all_values[-1]
            print(f"Останній рядок: {last_row}")
            
            # Перевіряємо, чи це тестовий запис
            if any("Тестовий" in str(cell) for cell in last_row):
                print("Це тестовий запис - видаляємо...")
                _sheet.delete_rows(total_rows)
                print("✅ Тестовий запис видалено")
            else:
                print("Це не тестовий запис - залишаємо")
        else:
            print("Немає рядків для видалення")
            
    except Exception as e:
        print(f"Помилка: {e}")

if __name__ == "__main__":
    remove_test_user()
