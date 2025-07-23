#!/usr/bin/env python3
"""
Перевіряє стан реєстрації для користувача з Telegram
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from telegram import Update
from telegram.ext import Application
import logging
from config.config import TELEGRAM_TOKEN as TOKEN

# Налаштування логування
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def check_user_state():
    """Перевіряє стан користувача в боті"""
    
    print("Перевіряємо стан користувача в боті...")
    
    # Створюємо додаток
    application = Application.builder().token(TOKEN).build()
    
    # Запускаємо application для доступу до context
    await application.initialize()
    
    # Тестуємо з реальним ID користувача (з скріншоту видно, що це тестовий бот)
    # Зазвичай context зберігається в persistence, якщо він налаштований
    
    print("Application ініціалізовано")
    
    # Перевіряємо, чи є persistence в боті
    if hasattr(application, 'persistence'):
        print(f"Persistence: {application.persistence}")
    else:
        print("Persistence не налаштовано - дані context втрачаються після перезапуску")
    
    await application.shutdown()

if __name__ == "__main__":
    import asyncio
    asyncio.run(check_user_state())
