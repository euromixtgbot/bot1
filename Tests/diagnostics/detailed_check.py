#!/usr/bin/env python3
"""
Детальна перевірка функцій Google Sheets
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from google_sheets_service import find_user_by_phone, _normalize_phone, _sheet, _HEADERS

def detailed_check():
    """Детально перевіряє роботу з Google Sheets"""
    print("=== ДЕТАЛЬНА ПЕРЕВІРКА GOOGLE SHEETS ===\n")
    
    test_phone = "+380999999999"
    
    print(f"1. Заголовки таблиці: {_HEADERS}")
    print(f"2. Тестовий номер: {test_phone}")
    print(f"3. Нормалізований номер: {_normalize_phone(test_phone)}")
    
    # Знаходимо останній рядок
    all_values = _sheet.get_all_values()
    last_row = all_values[-1]
    print(f"4. Останній рядок: {last_row}")
    
    # Створюємо словник з останнього рядка
    if len(last_row) == len(_HEADERS):
        last_record = {_HEADERS[i]: last_row[i] for i in range(len(_HEADERS))}
        print(f"5. Останній запис як словник: {last_record}")
        
        # Перевіряємо номер телефону в останньому записі
        mobile_in_record = last_record.get("mobile_number", "")
        print(f"6. Номер в записі: '{mobile_in_record}'")
        print(f"7. Нормалізований номер в записі: '{_normalize_phone(mobile_in_record)}'")
        
        if _normalize_phone(mobile_in_record) == _normalize_phone(test_phone):
            print("   ✅ Номери співпадають!")
        else:
            print("   ❌ Номери НЕ співпадають")
    
    # Пробуємо знайти через функцію
    print(f"\n8. Шукаємо через find_user_by_phone...")
    try:
        result = find_user_by_phone(test_phone)
        if result:
            print(f"   ✅ Знайдено: {result}")
        else:
            print(f"   ❌ НЕ знайдено")
    except Exception as e:
        print(f"   ❌ Помилка: {e}")

if __name__ == "__main__":
    detailed_check()
