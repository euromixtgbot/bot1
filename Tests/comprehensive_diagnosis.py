#!/usr/bin/env python3
"""
Детальна діагностика проблеми з файлами в Telegram Bot
Цей скрипт імітує весь процес відправки файлів для виявлення точної проблеми
"""

import sys
import os
import asyncio
import json
import logging
from typing import Dict, Any, Optional, List

# Налаштування logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Додаємо шляхи
sys.path.insert(0, '/home/Bot1')
sys.path.insert(0, '/home/Bot1/src')

async def test_telegram_token():
    """Тест 1: Перевіряємо чи є доступ до Telegram API"""
    print("🧪 ТЕСТ 1: Перевірка доступу до Telegram API")
    
    try:
        from config.config import TELEGRAM_TOKEN
        
        if not TELEGRAM_TOKEN:
            print("❌ TELEGRAM_TOKEN порожній!")
            return False
            
        print(f"✅ TELEGRAM_TOKEN: {TELEGRAM_TOKEN[:10]}...{TELEGRAM_TOKEN[-10:]}")
        
        # Перевіряємо з'єднання
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getMe")
            result = response.json()
            
            if result.get('ok'):
                bot_info = result.get('result', {})
                print(f"✅ Bot Info: {bot_info.get('username')} ({bot_info.get('first_name')})")
                return True
            else:
                print(f"❌ Telegram API Error: {result}")
                return False
                
    except Exception as e:
        print(f"❌ Помилка: {e}")
        return False

async def test_file_download_simulation():
    """Тест 2: Симуляція завантаження файлу з Jira"""
    print("\\n🧪 ТЕСТ 2: Симуляція завантаження файлу")
    
    try:
        # Імітуємо файл Excel
        excel_content = b"PK\\x03\\x04\\x14\\x00\\x00\\x00\\x08\\x00"  # Початок Excel файлу
        filename = "test.xlsx"
        mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        
        print(f"📁 Файл: {filename}")
        print(f"📋 MIME: {mime_type}")
        print(f"📊 Розмір: {len(excel_content)} bytes")
        
        # Імітуємо фото
        jpg_content = b"\\xff\\xd8\\xff\\xe0"  # Початок JPEG файлу
        photo_filename = "test.jpg"
        photo_mime = "image/jpeg"
        
        print(f"📸 Фото: {photo_filename}")
        print(f"📋 MIME: {photo_mime}")
        print(f"📊 Розмір: {len(jpg_content)} bytes")
        
        return [
            (filename, excel_content, mime_type),
            (photo_filename, jpg_content, photo_mime)
        ]
        
    except Exception as e:
        print(f"❌ Помилка: {e}")
        return []

async def test_telegram_api_methods():
    """Тест 3: Перевіряємо який метод API буде використано"""
    print("\\n🧪 ТЕСТ 3: Визначення методу Telegram API")
    
    test_files = [
        ("test.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 1024),
        ("test.jpg", "image/jpeg", 1024),
        ("test.txt", "text/plain", 1024),
        ("test.mp4", "video/mp4", 1024),
        ("test.mp3", "audio/mpeg", 1024),
    ]
    
    for filename, mime_type, file_size in test_files:
        # Логіка з send_telegram_message
        method = "sendDocument"  # Default
        file_param = "document"
        
        if mime_type.startswith('image/'):
            if file_size <= 10 * 1024 * 1024:  # 10MB
                method = "sendPhoto"
                file_param = "photo"
        elif mime_type.startswith('video/'):
            if file_size <= 50 * 1024 * 1024:  # 50MB
                method = "sendVideo"
                file_param = "video"
        elif mime_type.startswith('audio/'):
            if file_size <= 50 * 1024 * 1024:  # 50MB
                method = "sendAudio"
                file_param = "audio"
        
        print(f"📁 {filename} → {method} (param: {file_param})")

async def test_send_telegram_message_function():
    """Тест 4: Тестуємо реальну функцію send_telegram_message"""
    print("\\n🧪 ТЕСТ 4: Перевірка функції send_telegram_message")
    
    try:
        # Імпортуємо функцію
        from jira_webhooks2 import send_telegram_message
        
        # Тестові дані (невеликий файл)
        test_content = b"Test file content for debugging"
        test_filename = "debug_test.txt"
        test_mime = "text/plain"
        
        # Тестовий chat_id (використаємо невалідний для тесту)
        test_chat_id = "123456789"  # Невалідний chat_id для тесту
        test_message = "🧪 Тестове повідомлення з файлом"
        
        print(f"📤 Тестуємо відправку файлу: {test_filename}")
        print(f"💬 Chat ID: {test_chat_id}")
        
        # Викликаємо функцію
        result = await send_telegram_message(
            chat_id=test_chat_id,
            text=test_message,
            file_data=(test_filename, test_content, test_mime)
        )
        
        print(f"📋 Результат: {result}")
        return result
        
    except Exception as e:
        print(f"❌ Помилка в send_telegram_message: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_webhook_payload_processing():
    """Тест 5: Симуляція обробки webhook payload"""
    print("\\n🧪 ТЕСТ 5: Симуляція webhook з файлами")
    
    # Імітуємо webhook payload з файлами
    mock_webhook = {
        "webhookEvent": "comment_created",
        "comment": {
            "id": "12345",
            "body": "Test comment with files\\n\\n!289грн.JPG|data-attachment-id=123456!\\n!Черкаси е-драйв.xlsx|data-attachment-id=789012!",
            "author": {
                "displayName": "Test User",
                "emailAddress": "test@example.com"
            }
        },
        "issue": {
            "key": "TEST-123",
            "fields": {
                "summary": "Test Issue",
                "attachment": [
                    {
                        "id": "123456",
                        "filename": "289грн.JPG",
                        "size": 95432,
                        "mimeType": "image/jpeg",
                        "content": "https://euromix.atlassian.net/secure/attachment/123456/289грн.JPG"
                    },
                    {
                        "id": "789012",
                        "filename": "Черкаси е-драйв.xlsx",
                        "size": 15678,
                        "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "content": "https://euromix.atlassian.net/secure/attachment/789012/Черкаси%20е-драйв.xlsx"
                    }
                ]
            }
        }
    }
    
    print("📥 Webhook payload створено")
    print(f"📎 Знайдено {len(mock_webhook['issue']['fields']['attachment'])} вкладень:")
    
    for att in mock_webhook['issue']['fields']['attachment']:
        print(f"  - {att['filename']} ({att['mimeType']}) - {att['size']} bytes")
    
    # Перевіряємо логіку витягування
    try:
        # Симуляція логіки з handle_comment_created
        attachments = []
        
        # 1. Пошук в issue.fields.attachment (ключове виправлення)
        if 'issue' in mock_webhook and 'fields' in mock_webhook['issue']:
            if 'attachment' in mock_webhook['issue']['fields']:
                issue_attachments = mock_webhook['issue']['fields']['attachment']
                if issue_attachments:
                    attachments.extend(issue_attachments)
                    print(f"✅ Знайдено {len(issue_attachments)} вкладень на рівні issue")
        
        # 2. Пошук embedded файлів в тексті коментаря
        import re
        comment_body = mock_webhook['comment']['body']
        embedded_pattern = r'!([^|]+)\\|data-attachment-id=([^!]+)!'
        embedded_matches = re.findall(embedded_pattern, comment_body)
        
        print(f"🔍 Знайдено {len(embedded_matches)} embedded посилань:")
        for filename, att_id in embedded_matches:
            print(f"  - {filename} (ID: {att_id})")
        
        print(f"🎯 ЗАГАЛЬНА КІЛЬКІСТЬ ВКЛАДЕНЬ: {len(attachments)}")
        return len(attachments) > 0
        
    except Exception as e:
        print(f"❌ Помилка обробки webhook: {e}")
        return False

async def test_mime_type_detection():
    """Тест 6: Перевірка визначення MIME типів"""
    print("\\n🧪 ТЕСТ 6: Перевірка MIME типів")
    
    try:
        from attachment_processor import _infer_mime_type
        
        test_files = [
            "289грн.JPG",
            "Черкаси е-драйв.xlsx", 
            "document.pdf",
            "archive.zip",
            "text.txt"
        ]
        
        for filename in test_files:
            mime_type = _infer_mime_type(filename)
            print(f"📁 {filename} → {mime_type}")
            
        return True
        
    except Exception as e:
        print(f"❌ Помилка: {e}")
        return False

async def run_comprehensive_diagnosis():
    """Запускає всі тести для виявлення проблеми"""
    print("🚀 ЗАПУСК КОМПЛЕКСНОЇ ДІАГНОСТИКИ ФАЙЛІВ TELEGRAM BOT")
    print("=" * 60)
    
    results = {}
    
    # Тест 1: Telegram API
    results['telegram_api'] = await test_telegram_token()
    
    # Тест 2: Файли
    test_files = await test_file_download_simulation()
    results['file_simulation'] = len(test_files) > 0
    
    # Тест 3: API методи
    await test_telegram_api_methods()
    results['api_methods'] = True
    
    # Тест 4: Функція відправки
    results['send_function'] = await test_send_telegram_message_function()
    
    # Тест 5: Webhook обробка
    results['webhook_processing'] = await test_webhook_payload_processing()
    
    # Тест 6: MIME типи
    results['mime_types'] = await test_mime_type_detection()
    
    # Підсумок
    print("\\n" + "=" * 60)
    print("📋 РЕЗУЛЬТАТИ ДІАГНОСТИКИ:")
    
    all_passed = True
    for test_name, result in results.items():
        status = "✅ ПРОЙШОВ" if result else "❌ НЕ ПРОЙШОВ"
        print(f"  {test_name}: {status}")
        if not result:
            all_passed = False
    
    print("\\n🎯 ВИСНОВОК:")
    if all_passed:
        print("✅ Всі тести пройшли! Проблема може бути в реальних webhooks або налаштуваннях.")
    else:
        print("❌ Виявлено проблеми! Перевірте неуспішні тести.")
    
    return results

if __name__ == "__main__":
    asyncio.run(run_comprehensive_diagnosis())
