#!/usr/bin/env python3
"""
Створює тестовий файл стану для користувача з Telegram
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.user_state_service import save_registration_state


def create_test_user_state():
    """Створює тестовий файл стану для користувача"""
    # Використовуємо telegram_id з попередніх тестів (з скріншоту)
    test_telegram_id = 420723708925  # Приклад з попередніх повідомлень

    # Створюємо тестові дані реєстрації
    test_registration_data = {
        "phone": "+420723708925",
        "telegram_id": str(test_telegram_id),
        "telegram_username": "testuser",
        "full_name": "прізвище",
        "division": "Дніпро",
        "department": "Операційний департамент",
    }

    # Зберігаємо стан на етапі підтвердження
    success = save_registration_state(
        test_telegram_id, test_registration_data, "confirm"
    )

    if success:
        print(f"✅ Створено тестовий файл стану для користувача {test_telegram_id}")
        print(f"📋 Дані: {test_registration_data}")
        print("🔄 Етап: confirm")
        print(f"📁 Файл створено: /home/Bot1/user_states/user_{test_telegram_id}.json")
    else:
        print(f"❌ Помилка створення файлу стану для користувача {test_telegram_id}")


if __name__ == "__main__":
    create_test_user_state()
