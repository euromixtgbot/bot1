#!/usr/bin/env python3
"""
Діагностичний скрипт для перевірки стану бота та користувачів
"""
import asyncio
import sys
import os
import json

# Додаємо шлях до src
sys.path.append('/home/Bot1/src')
sys.path.append('/home/Bot1')

from src.services import find_user_by_jira_issue_key

async def diagnose():
    """Діагностика стану бота"""
    
    print("🔍 ДІАГНОСТИКА СТАНУ БОТА")
    print("=" * 50)
    
    # Перевіряємо за яким issue ми працюємо
    test_issue = "SD-42403"  # З картинки користувача
    
    print(f"🎯 Перевіряємо issue: {test_issue}")
    
    try:
        user_data = await find_user_by_jira_issue_key(test_issue)
        print(f"📋 Дані користувача з Jira: {json.dumps(user_data, ensure_ascii=False, indent=2)}")
        
        if user_data:
            telegram_id = user_data.get("telegram_id")
            print(f"📱 Telegram ID користувача: {telegram_id}")
            
            # Пояснюємо проблему
            print()
            print("💡 ПРОБЛЕМА:")
            print("Коли користувач з Telegram додає коментар до задачі,")
            print("бот повинен отримати ПІБ з контексту користувача.")
            print("Але контекст може бути порожнім якщо:")
            print("1. Користувач не авторизований через /start")
            print("2. Дані профілю не збережені")
            print("3. Бот був перезапущений і втратив контекст")
            print()
            
            print("🛠️ РІШЕННЯ:")
            print("Потрібно отримати ПІБ з Google Sheets за Telegram ID")
            print("і зберегти його в контексті або використати напряму")
            
        else:
            print("❌ Користувача не знайдено")
            
    except Exception as e:
        print(f"❌ Помилка: {e}")

if __name__ == "__main__":
    asyncio.run(diagnose())
