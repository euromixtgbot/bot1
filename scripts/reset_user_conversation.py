#!/usr/bin/env python3
"""
Скрипт для скидання стану ConversationHandler конкретного користувача
"""

import asyncio
import logging
import sys
import os

# Додаємо шлях до модулів проекту
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from telegram.ext import Application
from config.config import TELEGRAM_BOT_TOKEN

async def reset_user_conversation_state(user_id: str):
    """Скидає стан ConversationHandler для конкретного користувача"""
    
    # Створюємо Application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    try:
        # Ініціалізуємо Application
        await application.initialize()
        
        # Отримуємо ChatData для користувача
        user_data = application.user_data.get(int(user_id))
        
        if user_data:
            print(f"📋 Поточні дані користувача {user_id} в bot memory:")
            for key, value in user_data.items():
                print(f"  {key}: {value}")
            
            # Очищаємо дані ConversationHandler
            conversation_keys = [
                "full_name", "mobile_number", "division", "department", 
                "service", "description", "attached_photo", "registration",
                "registration_step", "awaiting_new_user_name"
            ]
            
            cleared_keys = []
            for key in conversation_keys:
                if key in user_data:
                    del user_data[key]
                    cleared_keys.append(key)
            
            if cleared_keys:
                print(f"✅ Очищено ключі з bot memory: {', '.join(cleared_keys)}")
            else:
                print("ℹ️  Ключі ConversationHandler не знайдені в bot memory")
        else:
            print(f"ℹ️  Дані користувача {user_id} не знайдені в bot memory")
            
        # Перевіряємо та очищаємо персистентний файл стану
        import os
        user_state_file = f"/home/Bot1/user_states/user_{user_id}.json"
        
        if os.path.exists(user_state_file):
            print(f"📁 Знайдено персистентний файл стану: {user_state_file}")
            
            # Читаємо вміст файлу
            try:
                with open(user_state_file, 'r', encoding='utf-8') as f:
                    import json
                    state_data = json.load(f)
                    print(f"📋 Вміст персистентного файлу:")
                    print(f"  registration_step: {state_data.get('state', {}).get('registration_step', 'N/A')}")
                    print(f"  type: {state_data.get('state', {}).get('type', 'N/A')}")
                    print(f"  last_updated: {state_data.get('last_updated', 'N/A')}")
                    
                    # Видаляємо файл
                    os.remove(user_state_file)
                    print(f"✅ Персистентний файл видалено")
                    
            except Exception as e:
                print(f"❌ Помилка при роботі з персистентним файлом: {e}")
        else:
            print(f"ℹ️  Персистентний файл стану не знайдено")
    
    except Exception as e:
        print(f"❌ Помилка: {e}")
    
    finally:
        await application.shutdown()

async def main():
    """Головна функція"""
    if len(sys.argv) != 2:
        print("Використання: python reset_user_conversation.py <user_id>")
        print("Приклад: python reset_user_conversation.py 5667252017")
        sys.exit(1)
    
    user_id = sys.argv[1]
    
    print(f"🔄 Скидання стану ConversationHandler для користувача {user_id}...")
    await reset_user_conversation_state(user_id)
    print("✅ Завершено!")

if __name__ == "__main__":
    asyncio.run(main())
