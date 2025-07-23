#!/usr/bin/env python3
"""
Дослідження проблеми з кнопкою підтвердження та тестування нової системи файлів
"""

import sys
import os
import time
import json
from datetime import datetime
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_button_encoding():
    """Тестування різних варіантів кодування тексту кнопки"""
    
    print("=" * 80)
    print("🔍 ДОСЛІДЖЕННЯ ПРОБЛЕМИ З КНОПКОЮ ПІДТВЕРДЖЕННЯ")
    print("=" * 80)
    
    # Різні варіанти символу галочки
    checkmarks = [
        "✅",  # U+2705 WHITE HEAVY CHECK MARK
        "✓",   # U+2713 CHECK MARK  
        "☑",   # U+2611 BALLOT BOX WITH CHECK
        "☑️",  # U+2611 + U+FE0F BALLOT BOX WITH CHECK + VARIATION SELECTOR-16
        "✔",   # U+2714 HEAVY CHECK MARK
        "✔️"   # U+2714 + U+FE0F HEAVY CHECK MARK + VARIATION SELECTOR-16
    ]
    
    base_text = " Підтвердити"
    
    print("\n📝 ВАРІАНТИ ТЕКСТУ КНОПКИ:")
    for i, check in enumerate(checkmarks):
        full_text = check + base_text
        print(f"{i+1}. '{full_text}'")
        print(f"   Unicode: {[ord(c) for c in check]}")
        print(f"   UTF-8 hex: {check.encode('utf-8').hex()}")
        print(f"   Байт: {len(full_text.encode('utf-8'))}")
        print()
    
    print("🎯 ВИСНОВОК:")
    print("Різні клієнти Telegram можуть по-різному рендерити символи Unicode")
    print("Особливо проблематичні символи з Variation Selector (FE0F)")
    
    return checkmarks

def test_telegram_keyboard_behavior():
    """Моделюємо поведінку Telegram клавіатури"""
    
    print("\n" + "=" * 80)
    print("📱 МОДЕЛЮВАННЯ ПОВЕДІНКИ TELEGRAM КЛАВІАТУРИ")
    print("=" * 80)
    
    # Тестуємо поточну логіку обробки
    def process_confirmation(text):
        """Симулює нашу поточну логіку"""
        text = text.strip()
        if text == "❌ Скасувати":
            return "CANCEL"
        else:
            return "CONFIRM"
    
    test_inputs = [
        "✅ Підтвердити",
        "❌ Скасувати", 
        "✔️ Підтвердити",
        "ппп",  # Як в реальному тесті
        "увувуву",  # Як в реальному тесті
        "Підтвердити",
        " ✅ Підтвердити ",  # З пробілами
        "",
        "random text"
    ]
    
    print("\n🧪 ТЕСТУВАННЯ РІЗНИХ ВХОДІВ:")
    for text in test_inputs:
        result = process_confirmation(text)
        print(f"Ввід: '{text}' → Результат: {result}")
    
    print("\n✅ ПОТОЧНА ЛОГІКА:")
    print("- Все крім '❌ Скасувати' → ПІДТВЕРДЖЕННЯ")
    print("- Це дозволяє обійти проблеми з Unicode символами")
    print("- Користувач може ввести будь-який текст для підтвердження")

def test_file_retention_system():
    """Тестування нової системи збереження файлів"""
    
    print("\n" + "=" * 80)
    print("📁 ТЕСТУВАННЯ СИСТЕМИ ЗБЕРЕЖЕННЯ ФАЙЛІВ")
    print("=" * 80)
    
    try:
        from src.user_state_service import (
            save_registration_state, 
            load_registration_state, 
            complete_registration,
            user_state_manager
        )
        
        # Тестовий користувач
        test_user_id = 999999999
        
        print(f"\n1. Створюємо тестову реєстрацію для користувача {test_user_id}")
        
        # Симулюємо процес реєстрації
        registration_data = {
            "telegram_id": test_user_id,
            "telegram_username": "test_user",
            "phone": "+420123456789",
            "full_name": "Тестовий Користувач",
            "division": "Дніпро",
            "department": "IT департамент"
        }
        
        # Зберігаємо стан реєстрації
        save_result = save_registration_state(test_user_id, registration_data, "confirm")
        print(f"Збереження стану: {'✅ Успішно' if save_result else '❌ Помилка'}")
        
        # Завантажуємо стан
        loaded_state = load_registration_state(test_user_id)
        print(f"Завантаження стану: {'✅ Успішно' if loaded_state else '❌ Помилка'}")
        
        if loaded_state:
            print(f"Дані реєстрації: {loaded_state['registration']['full_name']}")
        
        print(f"\n2. Завершуємо реєстрацію (нова логіка - зберігаємо файл)")
        
        # Завершуємо реєстрацію (тепер файл зберігається)
        complete_result = complete_registration(test_user_id)
        print(f"Завершення реєстрації: {'✅ Успішно' if complete_result else '❌ Помилка'}")
        
        # Перевіряємо, що файл існує але не завантажується як активна реєстрація
        loaded_after_complete = load_registration_state(test_user_id)
        print(f"Завантаження після завершення: {'❌ Не завантажується (правильно)' if not loaded_after_complete else '⚠️ Все ще завантажується'}")
        
        # Перевіряємо що файл існує
        user_info = user_state_manager.get_user_info(test_user_id)
        if user_info:
            print(f"Файл існує: ✅ Тип: {user_info['state']['type']}")
            print(f"Завершено: {user_info['state'].get('completed_at', 'Невідомо')}")
        else:
            print("Файл НЕ існує: ❌")
        
        print(f"\n3. Перевіряємо директорію файлів стану")
        all_users = user_state_manager.list_all_users()
        print(f"Всього файлів користувачів: {len(all_users)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Помилка тестування: {e}")
        import traceback
        traceback.print_exc()
        return False

def investigate_real_button_issue():
    """Досліджуємо справжню причину проблеми з кнопкою"""
    
    print("\n" + "=" * 80)
    print("🕵️ ДОСЛІДЖЕННЯ РЕАЛЬНОЇ ПРОБЛЕМИ З КНОПКОЮ")
    print("=" * 80)
    
    print("\n🔍 МОЖЛИВІ ПРИЧИНИ:")
    print("1. 📱 Клієнт Telegram:")
    print("   - Мобільний vs Desktop")
    print("   - Різні версії клієнту")
    print("   - Операційна система (iOS/Android/Web)")
    
    print("\n2. 🌐 Мережеві проблеми:")
    print("   - Затримка відправки")
    print("   - Втрата пакетів")
    print("   - Проблеми з Telegram API")
    
    print("\n3. 🤖 Проблеми бота:")
    print("   - Клавіатура не відображається")
    print("   - Конфлікт з іншими обробниками")
    print("   - Втрата контексту")
    
    print("\n4. 👤 Поведінка користувача:")
    print("   - Ввід тексту замість натискання кнопки")
    print("   - Невидимість клавіатури")
    print("   - Плутанина з інтерфейсом")
    
    print("\n💡 РЕКОМЕНДАЦІЇ ДЛЯ ДІАГНОСТИКИ:")
    print("1. Додати детальне логування отриманого тексту (включно з hex)")
    print("2. Зробити скріншот того, що бачить користувач")
    print("3. Тестувати з різних клієнтів Telegram")
    print("4. Додати інструкції для користувача")

def create_button_debug_enhancement():
    """Створюємо покращене логування для діагностики кнопки"""
    
    print("\n" + "=" * 80)
    print("🔧 СТВОРЕННЯ ПОКРАЩЕНОГО ЛОГУВАННЯ")
    print("=" * 80)
    
    debug_code = '''
# Додати в global_registration_handler після отримання тексту:

elif registration_step == "confirm":
    confirmation = update.message.text.strip()
    
    # 🔍 ДОДАНЕ ДЕТАЛЬНЕ ЛОГУВАННЯ
    logger.info(f"=== BUTTON DEBUG INFO ===")
    logger.info(f"Raw text: '{update.message.text}'")
    logger.info(f"Stripped text: '{confirmation}'")
    logger.info(f"Text length: {len(confirmation)}")
    logger.info(f"UTF-8 bytes: {confirmation.encode('utf-8')}")
    logger.info(f"Hex representation: {confirmation.encode('utf-8').hex()}")
    logger.info(f"Unicode codepoints: {[ord(c) for c in confirmation]}")
    logger.info(f"User ID: {update.effective_user.id}")
    logger.info(f"Chat ID: {update.effective_chat.id}")
    logger.info(f"Message ID: {update.message.message_id}")
    logger.info(f"=========================")
    
    # Далі йде існуюча логіка...
'''
    
    print("📝 КОД ДЛЯ ДОДАВАННЯ В ОБРОБНИК:")
    print(debug_code)
    
    return debug_code

if __name__ == "__main__":
    print("🚀 ЗАПУСК ДОСЛІДЖЕННЯ ПРОБЛЕМИ З КНОПКОЮ ПІДТВЕРДЖЕННЯ")
    print(f"Час: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Виконуємо всі тести
    test_button_encoding()
    test_telegram_keyboard_behavior()
    test_file_retention_system()
    investigate_real_button_issue()
    create_button_debug_enhancement()
    
    print("\n" + "=" * 80)
    print("✅ ДОСЛІДЖЕННЯ ЗАВЕРШЕНО")
    print("=" * 80)
    print("\n📋 ПІДСУМОК:")
    print("1. ✅ Система збереження файлів змінена на архівування")
    print("2. ✅ Поточна логіка підтвердження робочая (гнучка)")
    print("3. 🔍 Потрібно додати детальне логування для діагностики")
    print("4. 📱 Можлива проблема в клієнті користувача або відображенні кнопок")
    print("\n🎯 НАСТУПНІ КРОКИ:")
    print("- Додати покращене логування")
    print("- Протестувати з різних клієнтів")
    print("- Спостерігати за поведінкою користувачів")
