#!/usr/bin/env python3
"""
Скрипт для принудительного скидання стану ConversationHandler у живому боті
"""

import asyncio
import logging
import sys
import os

# Додаємо шлях до модулів проекту
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from telegram.ext import Application
from config.config import TELEGRAM_BOT_TOKEN

async def force_reset_conversation_handler(user_id: str):
    """Принудительно скидає стан ConversationHandler для користувача у живому боті"""
    
    # Створюємо Application з тим же token, що і живий бот
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    try:
        # Ініціалізуємо Application
        await application.initialize()
        
        print(f"🔍 Перевіряємо дані користувача {user_id} в Application...")
        
        # Перевіряємо bot_data
        bot_data = application.bot_data
        print(f"📊 Bot data keys: {list(bot_data.keys()) if bot_data else 'Немає'}")
        
        # Перевіряємо user_data
        user_data = application.user_data.get(int(user_id))
        if user_data:
            print(f"📋 User data для {user_id}:")
            for key, value in user_data.items():
                print(f"  {key}: {value}")
            
            # Очищаємо user_data
            user_data.clear()
            print(f"✅ User data очищено")
        else:
            print(f"ℹ️  User data для користувача {user_id} не знайдено")
            
        # Перевіряємо chat_data 
        chat_data = application.chat_data.get(int(user_id))
        if chat_data:
            print(f"📋 Chat data для {user_id}:")
            for key, value in chat_data.items():
                print(f"  {key}: {value}")
            
            # Очищаємо chat_data
            chat_data.clear()
            print(f"✅ Chat data очищено")
        else:
            print(f"ℹ️  Chat data для користувача {user_id} не знайдено")
            
        # Імітуємо завершення ConversationHandler
        print(f"🔄 Принудово завершуємо всі ConversationHandler для користувача {user_id}...")
        
        # Симулюємо END стан для всіх ConversationHandler
        # Це має очистити внутрішній стан ConversationHandler
        try:
            # Отримуємо всі обробники conversation
            all_handlers = []
            if hasattr(application, '_handlers'):
                for group_handlers in application._handlers.values():
                    all_handlers.extend(group_handlers)
            
            conv_handlers = [h for h in all_handlers if hasattr(h, 'states') and hasattr(h, 'conversations')]
            
            for conv_handler in conv_handlers:
                if hasattr(conv_handler, 'conversations'):
                    # Отримуємо conversation key для цього користувача
                    conv_key = (int(user_id), int(user_id))  # (user_id, chat_id)
                    if conv_key in conv_handler.conversations:
                        print(f"🔧 Знайдено активний ConversationHandler: {conv_handler.name if hasattr(conv_handler, 'name') else 'Unknown'}")
                        print(f"   Поточний стан: {conv_handler.conversations[conv_key]}")
                        # Видаляємо conversation
                        del conv_handler.conversations[conv_key]
                        print(f"✅ ConversationHandler видалено для користувача")
                        
        except Exception as conv_error:
            print(f"⚠️  Помилка при очищенні ConversationHandler: {conv_error}")
            
        print(f"🎯 Завершено принудове скидання для користувача {user_id}")
        
    except Exception as e:
        print(f"❌ Помилка: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await application.shutdown()

async def main():
    """Головна функція"""
    if len(sys.argv) != 2:
        print("Використання: python force_reset_conversation.py <user_id>")
        print("Приклад: python force_reset_conversation.py 5667252017")
        sys.exit(1)
    
    user_id = sys.argv[1]
    
    print(f"🚀 Принудове скидання ConversationHandler для користувача {user_id}...")
    await force_reset_conversation_handler(user_id)
    print("✅ Завершено!")

if __name__ == "__main__":
    asyncio.run(main())
