#!/usr/bin/env python3
"""
Перевірка _HEADERS в google_sheets_service
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from google_sheets_service import _HEADERS, _COLUMN_INDEX

def check_headers_mapping():
    """Перевіряє маппінг заголовків"""
    print("=== ПЕРЕВІРКА МАППІНГУ ЗАГОЛОВКІВ ===\n")
    
    print(f"_HEADERS: {_HEADERS}")
    print(f"_COLUMN_INDEX: {_COLUMN_INDEX}")
    
    print("\nТестовий запис:")
    test_record = {
        "telegram_id": "123456789",
        "telegram_username": "test_user",
        "mobile_number": "+380999999999",
        "full_name": "Тестовий Користувач"
    }
    
    print(f"test_record: {test_record}")
    
    print("\nВідповідність:")
    for col in _HEADERS:
        value = test_record.get(col, "")
        print(f"  {col} -> '{value}'")

if __name__ == "__main__":
    check_headers_mapping()
