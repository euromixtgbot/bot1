import json
import logging
import asyncio
import traceback
from typing import Dict, Any, Optional, List, Tuple
import re
import urllib.parse
import time
from collections import defaultdict
from io import BytesIO

import httpx
import requests
from aiohttp import web

from config.config import JIRA_DOMAIN, JIRA_API_TOKEN, JIRA_EMAIL, JIRA_REPORTER_ACCOUNT_ID, TELEGRAM_TOKEN
from src.services import find_user_by_jira_issue_key
from src.fixed_issue_formatter import format_issue_info, format_issue_text
from src.jira_attachment_utils import build_attachment_urls, download_file_from_jira, normalize_jira_domain
from src.attachment_processor import process_attachments_for_issue

# Ініціалізуємо логування
logger = logging.getLogger(__name__)

# === Константи ===
# Типи подій, на які реагуємо
EVENT_ISSUE_UPDATED = "jira:issue_updated"
EVENT_COMMENT_CREATED = "comment_created"
EVENT_ISSUE_CREATED = "jira:issue_created"
EVENT_ATTACHMENT_CREATED = "attachment_created"

# Кеш для зберігання відправлених повідомлень, щоб уникнути дублікатів
# Структура: {issue_key: [{"text": "message_text", "time": timestamp}]]}
# Зберігаємо тільки останні повідомлення за останні 5 хвилин
RECENT_MESSAGES_CACHE: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
CACHE_TTL = 300  # 5 minutes

# === Функції для обробки вебхуків ===

async def handle_webhook(request: web.Request) -> web.Response:
    """
    Головний обробник вебхуків від Jira.
    
    Args:
        request: Запит вебхука
        
    Returns:
        web.Response: Відповідь для Jira
    """
    try:
        # Load and validate webhook data
        try:
            webhook_data = await request.json()
            logger.debug(f"Webhook data: {json.dumps(webhook_data, indent=2, ensure_ascii=False)}")
        except ValueError:
            logger.error("Invalid JSON in webhook request")
            return web.json_response({"status": "error", "message": "Invalid JSON"}, status=400)
        
        # Визначаємо тип події
        event_type = webhook_data.get('webhookEvent', '')
        if not event_type:
            logger.warning("No event type in request")
            return web.json_response({"status": "error", "message": "Missing event type"}, status=400)
            
        logger.info(f"Обробка події: {event_type}")
        
        # Validate required fields based on event type
        if not await validate_webhook_data(webhook_data, event_type):
            logger.error(f"Invalid webhook data for event type: {event_type}")
            return web.json_response({"status": "error", "message": "Invalid webhook data"}, status=400)
        
        # Route to appropriate handler
        handler = None
        if event_type == EVENT_ISSUE_UPDATED:
            handler = handle_issue_updated
        elif event_type == EVENT_COMMENT_CREATED:
            handler = handle_comment_created
        elif event_type == EVENT_ISSUE_CREATED:
            handler = handle_issue_created
        elif event_type == EVENT_ATTACHMENT_CREATED:
            handler = handle_attachment_created
        else:
            logger.warning(f"Unsupported event type: {event_type}")
            return web.json_response({"status": "error", "message": f"Unsupported event type: {event_type}"}, status=400)
            
        try:
            await handler(webhook_data)
        except Exception as e:
            logger.error(f"Error in {event_type} handler: {str(e)}", exc_info=True)
            # Don't return error to Jira - we've already received the webhook
            # Just log it and return success to prevent retries
            
        return web.json_response({"status": "success", "message": f"Event processed: {event_type}"})
        
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
        return web.json_response({"status": "error", "message": "Internal server error"}, status=500)

async def validate_webhook_data(data: Dict[str, Any], event_type: str) -> bool:
    """
    Validates that the webhook data contains all required fields for the given event type.
    
    Args:
        data: The webhook data to validate
        event_type: The type of event being processed
        
    Returns:
        bool: True if the data is valid, False otherwise
    """
    try:
        if event_type == EVENT_ISSUE_UPDATED:
            return bool(
                data.get('issue', {}).get('key') and
                data.get('changelog', {}).get('items')
            )
            
        elif event_type == EVENT_COMMENT_CREATED:
            return bool(
                data.get('issue', {}).get('key') and
                data.get('comment', {}).get('author')
            )
            
        elif event_type == EVENT_ISSUE_CREATED:
            return bool(
                data.get('issue', {}).get('key') and
                data.get('issue', {}).get('fields', {}).get('creator')
            )
            
        elif event_type == EVENT_ATTACHMENT_CREATED:
            return bool(
                data.get('attachment') and
                (data.get('issue', {}).get('key') or
                 # Allow issue key to be extracted from attachment URL
                 any(url_field in data.get('attachment', {}) for url_field in ['self', 'content', 'url']))
            )
        # Handle 'issue_property_set' event type
        elif event_type == 'issue_property_set':
            # Add specific validation for 'issue_property_set' if needed, or simply return True if no specific validation is required yet.
            # For now, let's assume it's valid if it has an issue key.
            return bool(data.get('issue', {}).get('key'))
            
        return False
        
    except Exception as e:
        logger.error(f"Error validating webhook data: {str(e)}", exc_info=True)
        return False

def get_status_emoji(status: str) -> str:
    """
    Повертає емодзі залежно від статусу задачі.
    
    Args:
        status: Назва статусу задачі
        
    Returns:
        str: Емодзі, що відповідає статусу
    """
    status_lower = status.lower()
    
    # Статуси "В очікуванні"
    if any(word in status_lower for word in ['очікуванні', 'ожидании', 'pending', 'waiting']):
        return "🔵"
    
    # Статуси "В роботі"
    if any(word in status_lower for word in ['роботі', 'работе', 'progress', 'doing', 'active']):
        return "🔵"
    
    # Статуси "Виконано/Закрито"
    if any(word in status_lower for word in ['виконано', 'выполнено', 'закрито', 'закрыто', 'done', 'closed', 'resolved']):
        return "🟢"
    
    # Статуси "Відкрито/Новий"
    if any(word in status_lower for word in ['відкрито', 'открыто', 'новий', 'новая', 'open', 'new', 'to do']):
        return "⚪️"
    
    # Статуси "Тестування"
    if any(word in status_lower for word in ['тестування', 'тестирование', 'testing', 'review']):
        return "🔵"
    
    # За замовчуванням
    return "🔵"

async def handle_issue_updated(webhook_data: Dict[str, Any]) -> None:
    """
    Обробка події оновлення задачі в Jira.
    Перевіряє зміну статусу та надсилає повідомлення користувачу в Telegram.
    """
    try:
        # Перевіряємо, чи змінився статус задачі
        changelog = webhook_data.get('changelog', {})
        items = changelog.get('items', [])
        
        # Шукаємо зміни статусу
        status_change = next((item for item in items if item.get('field') == 'status'), None)
        
        if not status_change:
            logger.info("Зміна задачі не пов'язана зі зміною статусу")
            return
        
        # Отримуємо дані про нове значення статусу
        new_status = status_change.get('toString', '')
        old_status = status_change.get('fromString', '')
        
        # Отримуємо дані про задачу
        issue_key = webhook_data.get('issue', {}).get('key', '')
        issue_summary = webhook_data.get('issue', {}).get('fields', {}).get('summary', '')
        
        logger.info(f"Статус задачі {issue_key} змінився з '{old_status}' на '{new_status}'")
        
        # Перевіряємо, від якого користувача надійшла зміна
        author_info = None
        if 'user' in webhook_data:
            author_info = webhook_data.get('user', {})
        else:
            # Спроба знайти автора в інших місцях
            author_info = webhook_data.get('comment', {}).get('author', {})
            
        # Якщо зміна від технічного користувача - ігноруємо
        if author_info:
            from config.config import JIRA_REPORTER_ACCOUNT_ID
            author_id = author_info.get('accountId', '')
            if author_id == JIRA_REPORTER_ACCOUNT_ID:
                logger.info(f"Пропускаємо зміну статусу від технічного користувача (ID: {author_id})")
                return
                
        # Знаходимо користувача в Telegram за ключем задачі
        user_data = await find_user_by_jira_issue_key(issue_key)
        
        if not user_data:
            logger.warning(f"Не знайдено користувача Telegram для задачі {issue_key}")
            return
        
        # Готуємо повідомлення про зміну статусу в новому форматі
        status_emoji = get_status_emoji(new_status)
        message = (
            f"🆕 <b>Статус задачі💡{issue_key} оновлено:</b>\n\n"
            f"{status_emoji} <b>{new_status}</b>❔"
        )
        
        # Перевіряємо чи повідомлення є дублікатом
        if is_duplicate_message(issue_key, message):
            logger.info(f"Пропускаємо дублікат повідомлення для задачі {issue_key}")
            return
        
        # Додаємо повідомлення до кешу
        add_message_to_cache(issue_key, message)
        
        # Надсилаємо повідомлення користувачу в Telegram
        await send_telegram_message(user_data['telegram_id'], message)
        
    except Exception as e:
        logger.error(f"Помилка обробки зміни статусу задачі: {str(e)}", exc_info=True)

async def handle_comment_created(webhook_data: Dict[str, Any]) -> None:
    """
    Обробка події створення коментаря в Jira.
    Пересилає коментар користувачу в Telegram.
    """
    try:
        # Get comment and issue data
        comment = webhook_data.get('comment', {})
        issue_key = webhook_data.get('issue', {}).get('key', '')
        
        logger.info(f"Processing new comment for issue {issue_key}")
        logger.debug(f"Full webhook data: {json.dumps(webhook_data, indent=2, ensure_ascii=False)}")
        
        # Skip if empty comment and no attachments
        comment_body = comment.get('body', '').strip()
        
        # Skip comments from system/bot users
        comment_author = comment.get('author', {})
        author_name = comment_author.get('displayName', '')
        author_id = comment_author.get('accountId', '')
        
        logger.debug(f"Comment author: {author_name} (ID: {author_id})")
        
        from config.config import JIRA_REPORTER_ACCOUNT_ID
        if "Telegram Bot" in author_name or author_id == JIRA_REPORTER_ACCOUNT_ID:
            logger.info(f"Skipping comment from system user: {author_name}")
            return
        
        # Find Telegram user
        user_data = await find_user_by_jira_issue_key(issue_key)
        if not user_data:
            logger.warning(f"No Telegram user found for issue {issue_key}")
            return
            
        logger.debug(f"Found Telegram user: {user_data}")
        
        # Collect all attachments from different possible locations
        attachments = []
        
        # 1. Direct attachments on the comment
        if 'attachment' in comment:
            direct_attachments = comment.get('attachment', [])
            logger.debug(f"Found {len(direct_attachments)} direct attachments")
            attachments.extend(direct_attachments)
            
        if 'attachments' in comment:
            plural_attachments = comment.get('attachments', [])
            logger.debug(f"Found {len(plural_attachments)} attachments in plural form")
            attachments.extend(plural_attachments)
            
        # 2. Embedded attachments in comment body
        if comment_body:
            embedded = extract_embedded_attachments(comment_body)
            if embedded:
                logger.info(f"Found {len(embedded)} embedded attachments in comment")
                logger.debug(f"Embedded attachments: {json.dumps(embedded, indent=2)}")
                attachments.extend(embedded)
                
        # 3. Special content structure (some Jira versions)
        if 'content' in comment:
            content = comment.get('content', [])
            for item in content:
                if isinstance(item, dict) and 'attachment' in item:
                    logger.debug(f"Found attachment in content structure: {json.dumps(item['attachment'], indent=2)}")
                    attachments.append(item['attachment'])
                    
        # Log attachment info
        if attachments:
            logger.info(f"Found {len(attachments)} total attachments")
            for idx, att in enumerate(attachments, 1):
                filename = att.get('filename', 'unknown')
                att_id = att.get('id', 'no-id')
                att_url = att.get('content', att.get('self', ''))
                logger.info(f"Attachment {idx}: {filename} (ID: {att_id})")
                logger.debug(f"Attachment {idx} details: {json.dumps(att, indent=2)}")
                
        # Prepare and send the message
        message_parts = []
        
        # Add comment text if present
        if comment_body:
            formatted_text = format_comment_text(comment_body)
            if formatted_text:  # Only add if there's actual content after formatting
                message_parts.extend([
                    "🔔 <b>Відповідь техпідтримки:</b>\n\n",
                    formatted_text
                ])
        # Не додаємо блок про вкладення у текстове повідомлення
        # Send main message (only if there's text content)
        message = "\n".join(message_parts)
        if message:
            await send_telegram_message(user_data['telegram_id'], message)
            
        # Process and send attachments
        if attachments:
            logger.info("Starting to process attachments")
            await process_attachments(attachments, issue_key, user_data['telegram_id'])
            
    except Exception as e:
        logger.error(f"Error processing new comment: {str(e)}", exc_info=True)
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")

async def handle_issue_created(webhook_data: Dict[str, Any]) -> None:
    """
    Обробка події створення задачі в Jira.
    Надсилає повідомлення в Telegram, якщо задача створена не через бот.
    """
    try:
        # Отримуємо дані про задачу
        issue = webhook_data.get('issue', {})
        issue_key = issue.get('key', '')
        issue_summary = issue.get('fields', {}).get('summary', '')
        issue_creator = issue.get('fields', {}).get('creator', {}).get('displayName', '')
        
        logger.info(f"Створена нова задача {issue_key} користувачем {issue_creator}: {issue_summary[:100]}...")
        
        # Перевіряємо чи задача не створена через бот
        if "Telegram Bot" in issue_creator:
            logger.info(f"Пропускаємо повідомлення про задачу, створену через бот")
            return
        
        # Отримуємо telegram_id користувача зі спеціального поля або через пошук
        telegram_id = None
        
        # Шукаємо в спеціальних полях
        custom_fields = issue.get('fields', {})
        for field_key, field_value in custom_fields.items():
            if field_key == 'customfield_10145':  # telegram_id поле
                telegram_id = field_value
                break
        
        if not telegram_id:
            logger.warning(f"Не знайдено Telegram ID для задачі {issue_key}")
            return
        
        # Форматуємо деталі задачі за допомогою наших функцій форматування
        formatted_issue = format_issue_info(issue)
        issue_text = format_issue_text(formatted_issue)
        
        # Готуємо повідомлення про створення задачі
        message = (
            f"🆕 <b>Створено нову задачу</b>\n\n"
            f"{issue_text}"
        )
        
        # Перевіряємо чи повідомлення є дублікатом
        if is_duplicate_message(issue_key, message):
            logger.info(f"Пропускаємо дублікат повідомлення для задачі {issue_key}")
            return
        
        # Додаємо повідомлення до кешу
        add_message_to_cache(issue_key, message)
        
        # Надсилаємо повідомлення користувачу в Telegram
        await send_telegram_message(telegram_id, message)

    except Exception as e:
        logger.error(f"Помилка обробки нової задачі: {str(e)}", exc_info=True)

async def handle_attachment_created(webhook_data: Dict[str, Any]) -> None:
    """
    Обробка події створення вкладення в Jira.
    Зберігає інформацію про вкладення і надсилає його в Telegram.
    """
    try:
        # Логуємо повні дані вебхука для відлагодження
        logger.debug(f"Отримано подію attachment_created: {json.dumps(webhook_data, indent=2)}")
        
        # Отримуємо дані про вкладення
        attachment = webhook_data.get('attachment', {})
        if isinstance(attachment, list):
            attachment = attachment[0] if attachment else {}
        if not attachment:
            logger.warning("Отримано подію attachment_created без даних вкладення")
            return
            
        attachment_id = attachment.get('id', '')
        attachment_url = attachment.get('self', '')
        filename = attachment.get('filename', 'файл')
        
        logger.info(f"Обробка події створення вкладення: {filename} (ID: {attachment_id})")
        logger.debug(f"Деталі вкладення: {json.dumps(attachment, indent=2)}")
        
        # Отримуємо дані про задачу, до якої належить вкладення
        issue_key = None
        
        # Спочатку шукаємо ключ задачі в даних вебхука
        if 'issue' in webhook_data:
            issue = webhook_data.get('issue', {})
            issue_key = issue.get('key', '')
            logger.info(f"Знайдено ключ задачі в даних вебхука: {issue_key}")
            
        # Спосіб 1: Отримання issue_key через REST API, якщо маємо attachment_id
        if not issue_key and attachment_id:
            max_retries = 3
            base_retry_delay = 1  # Start with 1 second
            api_url = f"https://{JIRA_DOMAIN}/rest/api/3/attachment/{attachment_id}"
            auth = httpx.BasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
            headers = {
                'X-Atlassian-Token': 'no-check',
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Connection': 'keep-alive'
            }
            
            for attempt in range(max_retries):
                try:
                    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
                    transport = httpx.AsyncHTTPTransport(
                        retries=3,
                        verify=True,
                        http2=True,
                        limits=limits
                    )
                    async with httpx.AsyncClient(
                        timeout=30.0,
                        auth=auth,
                        transport=transport,
                        verify=True,
                        limits=limits,
                        http2=True,
                        trust_env=True  # Added this line
                    ) as client:
                        response = await client.get(api_url, headers=headers)
                        response.raise_for_status()
                        attachment_info = response.json()
                        
                        # В різних версіях Jira може бути різне поле
                        for field in ['issueId', 'issueKey', 'issue']:
                            if field in attachment_info:
                                value = attachment_info[field]
                                if isinstance(value, dict):
                                    issue_key = value.get('key', '')
                                else:
                                    issue_key = value
                                if issue_key:
                                    logger.info(f"Знайдено ключ задачі через API: {issue_key}")
                                    break
                        if issue_key:
                            break  # Found the issue key, exit retry loop
                            
                except httpx.ConnectError as conn_error:
                    logger.warning(f"Connection error (attempt {attempt + 1}/{max_retries}): {str(conn_error)}")
                    if attempt < max_retries - 1:
                        retry_delay = min(base_retry_delay * (2 ** attempt), 60)  # Exponential backoff, max 60s
                        logger.info(f"Waiting {retry_delay} seconds before retry...")
                        await asyncio.sleep(retry_delay)
                        continue
                    logger.error(f"Failed to connect to Jira API after {max_retries} attempts: {str(conn_error)}")
                    
                except httpx.HTTPError as http_error:
                    logger.warning(f"HTTP error (attempt {attempt + 1}/{max_retries}): {str(http_error)}")
                    if attempt < max_retries - 1:
                        retry_delay = min(base_retry_delay * (2 ** attempt), 60)
                        logger.info(f"Waiting {retry_delay} seconds before retry...")
                        await asyncio.sleep(retry_delay)
                        continue
                    logger.error(f"HTTP request to Jira API failed after {max_retries} attempts: {str(http_error)}")
                    
                except Exception as e:
                    logger.error(f"Unexpected error accessing Jira API: {str(e)}")
                    break
        
        # Спосіб 2: Якщо все ще немає ключа, пробуємо знайти в URL
        if not issue_key:
            urls_to_check = []
            
            # Збираємо всі можливі URL з різних полів
            urls_to_check = set()  # Використовуємо set для уникнення дублікатів
            
            if attachment_url:
                urls_to_check.add(attachment_url)
            if attachment.get('content'):
                urls_to_check.add(attachment.get('content'))
            if attachment.get('url'):
                urls_to_check.add(attachment.get('url'))
            if attachment.get('self'):
                urls_to_check.add(attachment.get('self'))
            
            # Додаємо додаткові URL, які можуть містити issue_key
            if attachment_id:
                urls_to_check.add(f"https://{JIRA_DOMAIN}/secure/attachment/{attachment_id}")
                urls_to_check.add(f"https://{JIRA_DOMAIN}/rest/api/3/attachment/{attachment_id}")
            
            logger.debug(f"URLs to check for issue_key: {list(urls_to_check)}")
                
            for url in urls_to_check:
                # Різні можливі формати URL
                patterns = [
                    r'/issue/([^/]+)/attachment',              # Стандартний формат
                    r'/([A-Z]+-\d+)/attachments',              # Альтернативний формат
                    r'/secure/attachment/[0-9a-f-]+/([A-Z]+-\d+)', # Формат з UUID
                    r'/projects/[^/]+/issues/([^/]+)',         # Project issues формат
                    r'/([A-Z]+-\d+)/content',                  # Формат контенту
                    r'selectedIssue=([A-Z]+-\d+)',            # Параметр в URL
                    r'issueKey=([A-Z]+-\d+)'                  # Інший параметр в URL
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, url)
                    if match:
                        found_key = match.group(1)
                        # Перевіряємо, що знайдений ключ має правильний формат (напр. SD-40461)
                        if re.match(r'^[A-Z]+-\d+$', found_key):
                            issue_key = found_key
                            logger.info(f"Витягнуто ключ задачі з URL: {issue_key}")
                            break
                
                if issue_key:
                    break
        
        if not issue_key:
            logger.warning(f"Не вдалося визначити ключ задачі для вкладення {attachment_id}")
            return
            
        logger.info(f"Вкладення {filename} (ID: {attachment_id}) належить до задачі {issue_key}")
        
        # Знаходимо користувача в Telegram для надсилання сповіщення
        user_data = await find_user_by_jira_issue_key(issue_key)
        if not user_data:
            logger.warning(f"Не знайдено користувача Telegram для задачі {issue_key}")
            return
        
        # Підготовка повідомлення
        icon = "📎" # Default icon
        message = f"📎 <b>Нове вкладення до задачі {issue_key}:</b>\n\n📎 <b>{filename}</b>"
        
        # Перевіряємо чи повідомлення є дублікатом
        if is_duplicate_message(issue_key, message):
            logger.info(f"Пропускаємо дублікат повідомлення для задачі {issue_key}")
            return
            
        # Додаємо повідомлення до кешу
        add_message_to_cache(issue_key, message)
        
        # Підготовка списку вкладень для обробки
        # Додаємо chat_id до інформації про вкладення для використання в callback
        attachment['chat_id'] = user_data['telegram_id']
        
        # Використовуємо новий метод обробки вкладень
        logger.info(f"Починаємо обробку вкладення {filename} за допомогою attachment_processor")
        try:
            success, errors = await process_attachments_for_issue(
                JIRA_DOMAIN, 
                [attachment], 
                issue_key, 
                send_attachment_to_telegram
            )
            
            if errors > 0:
                logger.warning(f"Деякі вкладення не вдалося обробити ({errors} помилок)")
                # Send notification about failed download
                error_message = f"⚠️ <b>Помилка завантаження вкладення до задачі {issue_key}</b>\n\n" \
                              f"На жаль, не вдалося завантажити файл: {filename}\n" \
                              f"Спробуйте відкрити його безпосередньо в Jira."
                await send_telegram_message(user_data['telegram_id'], error_message)
        except Exception as e:
            logger.error(f"Помилка при обробці вкладення {filename}: {str(e)}", exc_info=True)
            error_message = f"⚠️ <b>Помилка завантаження вкладення до задачі {issue_key}</b>\n\n" \
                          f"На жаль, не вдалося завантажити файл: {filename}\n" \
                          f"Спробуйте відкрити його безпосередньо в Jira."
            await send_telegram_message(user_data['telegram_id'], error_message)
            
        # The attachment is handled by send_attachment_to_telegram callback, no need for additional processing
        return
                
    except Exception as e:
        logger.error(f"Помилка обробки події створення вкладення: {str(e)}", exc_info=True)

# === Допоміжні функції ===

async def send_telegram_message(chat_id: str, text: str, file_data: Optional[tuple] = None) -> bool:
    """
    Надсилає повідомлення користувачу в Telegram.
    
    Args:
        chat_id: ID чату користувача в Telegram
        text: Текст повідомлення
        file_data: Кортеж (filename, file_content, mime_type) для надсилання файлу
        
    Returns:
        bool: True якщо повідомлення надіслано успішно
    """
    try:
        # Базові налаштування для HTTP клієнта
        base_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
        
        # Для файлів використовуємо спеціальну обробку
        if file_data:
            filename, file_content, mime_type = file_data
            if not file_content:
                logger.error("Файл порожній або відсутній")
                return False
                
            # Використовуємо httpx для асинхронних запитів з підвищеним timeout
            async with httpx.AsyncClient(timeout=60.0) as client:
                try:
                    # Визначаємо метод відправки в залежності від типу файлу
                    method = "sendDocument"  # Default method
                    file_param = "document"  # Default parameter name
                    
                    # Select appropriate method based on MIME type and file size
                    if mime_type.startswith('image/'):
                        if len(file_content) <= 10 * 1024 * 1024:  # Max 10MB for photos
                            method = "sendPhoto"
                            file_param = "photo"
                            
                    elif mime_type.startswith('video/'):
                        if len(file_content) <= 50 * 1024 * 1024:  # Max 50MB for videos
                            method = "sendVideo"
                            file_param = "video"
                            
                    elif mime_type.startswith('audio/'):
                        if len(file_content) <= 50 * 1024 * 1024:  # Max 50MB for audio
                            method = "sendAudio"
                            file_param = "audio"
                    
                    logger.debug(f"Using Telegram API method: {method}")
                    
                    # Готуємо дані для відправки
                    files = {
                        file_param: (filename, BytesIO(file_content), mime_type)
                    }
                    data = {
                        'chat_id': chat_id,
                        'caption': text[:1024] if text else None,  # Limit caption to 1024 chars
                        'parse_mode': 'HTML'
                    }
                    
                    # For large files, set a longer timeout
                    file_size_mb = len(file_content) / (1024 * 1024)
                    timeout = max(30, min(300, int(file_size_mb * 5)))  # 5 seconds per MB, min 30s, max 300s
                    
                    logger.debug(f"Sending file {filename} ({mime_type}) of size {file_size_mb:.2f} MB with {timeout}s timeout")
                    logger.debug(f"Request data: {data}")
                    
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        response = await client.post(f"{base_url}/{method}", data=data, files=files)
                        logger.debug(f"API Response status: {response.status_code}")
                        
                        response.raise_for_status()
                        response_json = response.json()
                        
                        if not response_json.get('ok'):
                            error_msg = response_json.get('description', 'Unknown error')
                            logger.error(f"Telegram API error: {error_msg}")
                            
                            # If file is too large for selected method, try sendDocument
                            if 'file is too big' in error_msg.lower() and method != "sendDocument":
                                logger.info(f"File too big for {method}, falling back to sendDocument")
                                files = {
                                    'document': (filename, BytesIO(file_content), mime_type)
                                }
                                response = await client.post(f"{base_url}/sendDocument", data=data, files=files)
                                response.raise_for_status()
                                response_json = response.json()
                        
                        logger.info(f"File {filename} sent successfully")
                        logger.debug(f"Telegram API response: {json.dumps(response_json, indent=2)}")
                        
                        return True
                        
                except Exception as e:
                    logger.error(f"Error sending file {filename}: {str(e)}", exc_info=True)
                    
                    # Try to get more info about the error
                    error_details = str(e)
                    try:
                        if hasattr(e, 'response') and e.response:
                            error_details = f"{e} - Response: {e.response.text}"
                    except:
                        pass
                    
                    logger.error(f"Error details: {error_details}")
                    
                    # If file is too large, try to send as a link
                    if 'Request entity too large' in str(e) or 'file is too big' in str(e).lower():
                        logger.info("File too large for Telegram, sending as a link")
                        link_text = f"{text}\n\n⚠️ <i>Файл завеликий для надсилання в Telegram. " \
                                  f"Будь ласка, завантажте його безпосередньо з Jira.</i>"
                        return await send_telegram_message(chat_id, link_text)
                    
                    return False
        
        # Для звичайних текстових повідомлень
        else:
            # Обмежуємо довжину повідомлення до 4096 символів (ліміт Telegram)
            if len(text) > 4096:
                text = text[:4093] + '...'
                
            data = {
                'chat_id': chat_id,
                'text': text,
                'parse_mode': 'HTML'
            }
            
            # Надсилаємо повідомлення
            async with httpx.AsyncClient() as client:
                response = await client.post(f"{base_url}/sendMessage", json=data)
                response.raise_for_status()
                
                logger.debug(f"Message sent successfully: {text[:100]}...")
                return True
                
    except Exception as e:
        logger.error(f"Error sending message to Telegram: {str(e)}", exc_info=True)
        return False

async def send_telegram_text(chat_id: str, text: str) -> bool:
    """
    Допоміжна функція для надсилання текстових повідомлень в Telegram.
    
    Args:
        chat_id: ID чату користувача в Telegram
        text: Текст повідомлення (може містити HTML)
        
    Returns:
        bool: True, якщо повідомлення успішно надіслано
    """
    try:
        from config.config import TELEGRAM_BOT_TOKEN
        import requests
        
        tg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }
        
        response = requests.post(tg_url, json=data)
        
        if response.status_code == 200:
            logger.info(f"Повідомлення успішно надіслано")
            return True
        else:
            logger.error(f"Помилка надсилання повідомлення: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Помилка надсилання текстового повідомлення в Telegram: {str(e)}", exc_info=True)
        return False

def format_comment_text(text: str) -> str:
    """
    Форматує текст коментаря для Telegram, обробляє розмітку Jira.
    Видаляє зайву інформацію про вкладення та інлайн-зображення.
    
    Args:
        text: Вихідний текст коментаря
        
    Returns:
        str: Відформатований текст
    """
    if not text:
        return text

    import re
    # Видаляємо розмітку зображень !image.jpg|width=719,height=1280,alt="image.jpg"!
    text = re.sub(r'!([^|!]+)(\|[^!]+)?!', '', text)
    # Видаляємо рядки з посиланнями на вкладення (наприклад, \n📎 Прикріплені файли: ...)
    text = re.sub(r'\n?📎 Прикріплені файли:[^\n]*(\n|$)', '', text)
    text = re.sub(r'\n?• [^\n]+(\n|$)', '', text)
    # Видаляємо зайві пробіли та порожні рядки
    text = re.sub(r'\n\s*\n', '\n', text)
    text = text.strip()
    # Конвертуємо Jira bold в HTML
    text = re.sub(r'\*([^*]+)\*', r'<b>\1</b>', text)
    # Конвертуємо Jira italic в HTML
    text = re.sub(r'_([^_]+)_', r'<i>\1</i>', text)
    return text

def is_duplicate_message(issue_key: str, message_text: str, has_attachment: bool = False) -> bool:
    """
    Перевіряє, чи повідомлення вже було нещодавно відправлено для цієї задачі.
    Використовується для запобігання дублікатів повідомлень.
    
    Args:
        issue_key: Ключ задачі
        message_text: Текст повідомлення для перевірки
        has_attachment: True якщо повідомлення містить вкладення
        
    Returns:
        bool: True якщо повідомлення є дублікатом
    """
    # Якщо є вкладення, пропускаємо перевірку на дублікати
    if has_attachment:
        return False
        
    if issue_key not in RECENT_MESSAGES_CACHE:
        return False
        
    normalized_text = " ".join(message_text.split()).lower()
    
    for cached_msg in RECENT_MESSAGES_CACHE[issue_key]:
        cached_text = " ".join(cached_msg["text"].split()).lower()
        if cached_text == normalized_text or cached_text in normalized_text or normalized_text in cached_text:
            return True
            
    return False

def add_message_to_cache(issue_key: str, message_text: str) -> None:
    """
    Додає повідомлення до кешу для виявлення дублікатів.
    
    Args:
        issue_key: Ключ задачі
        message_text: Текст відправленого повідомлення
    """
    RECENT_MESSAGES_CACHE[issue_key].append({
        "text": message_text,
        "timestamp": time.time()
    })

def cleanup_message_cache() -> None:
    """Видаляє старі повідомлення з кешу."""
    current_time = time.time()
    
    for issue_key in list(RECENT_MESSAGES_CACHE.keys()):
        # Відфільтровуємо тільки актуальні повідомлення
        recent_messages = [
            msg for msg in RECENT_MESSAGES_CACHE[issue_key]
            if current_time - msg["timestamp"] < CACHE_TTL
        ]
        
        if recent_messages:
            RECENT_MESSAGES_CACHE[issue_key] = recent_messages
        else:
            del RECENT_MESSAGES_CACHE[issue_key]

# Функція для інтеграції з основним застосунком
async def setup_webhook_server(app, host: str, port: int, ssl_context: Optional[Any] = None):
    """
    Налаштовує і запускає веб-сервер для обробки вебхуків.
    
    Args:
        app: Об'єкт застосунку Telegram
        host: Хост для запуску веб-сервера
        port: Порт для запуску веб-сервера
        ssl_context: SSL-контекст для захищеного з'єднання
    """
    # Створюємо веб-застосунок aiohttp з більшим максимальним розміром тіла запиту
    web_app = web.Application(client_max_size=50 * 1024 * 1024)  # 50MB limit
    
    # Налаштовуємо маршрути
    web_app.router.add_post('/rest/webhooks/webhook1', handle_webhook)
    
    # Налаштуємо додатковий маршрут для простої перевірки роботи вебхуку
    async def ping(request):
        return web.json_response({
            "status": "ok",
            "message": "Webhook server is running",
            "max_size": "50MB"
        })
        
    web_app.router.add_get('/rest/webhooks/ping', ping)
    
    # Запускаємо веб-сервер
    runner = web.AppRunner(web_app)
    await runner.setup()
    
    # Створюємо сайт і запускаємо його
    # Завжди використовуємо HTTP, оскільки Nginx обробляє SSL
    site = web.TCPSite(runner, host, port)
    logger.info(f"Запускаємо вебхук-сервер HTTP на {host}:{port} (SSL обробляє Nginx)")
    
    await site.start()
    logger.info(f"Сервер вебхуків запущено на {host}:{port} з лімітом розміру запиту 50MB")
    
    return runner

async def send_attachment_to_telegram(attachment_data: dict) -> bool:
    """
    Callback function for sending attachments to Telegram.
    Used by the attachment processor.
    
    Args:
        attachment_data: Dict with keys:
            - chat_id: str
            - file_name: str
            - file_bytes: bytes
            - mime_type: str
            - issue_key: str
            
    Returns:
        bool: True if message was sent successfully
    """
    try:
        chat_id = attachment_data.get('chat_id', '')
        filename = attachment_data.get('file_name', '')
        file_bytes = attachment_data.get('file_bytes', b'')
        mime_type = attachment_data.get('mime_type', '')
        issue_key = attachment_data.get('issue_key', '')
        file_size = len(file_bytes) if file_bytes else 0
        
        if not file_bytes:
            logger.error("Empty file content provided to send_attachment_to_telegram")
            return False
        
        # Size limits based on Telegram API constraints    
        size_limit = 50 * 1024 * 1024  # 50MB default
        if mime_type.startswith('image/'):
            size_limit = 10 * 1024 * 1024  # 10MB for photos
            
        # Prepare message text
        icon = "🖼️" if mime_type.startswith('image/') else "📎"
        file_size_mb = file_size / (1024 * 1024)
        file_info = f"{filename} ({file_size_mb:.1f} MB)"
        message = f"{icon} <b>Вкладення до задачі {issue_key}:</b>\n\n📎 <b>{file_info}</b>"
        
        # Check file size limit
        if file_size > size_limit:
            warning_msg = (f"{message}\n\n⚠️ <i>Файл завеликий для надсилання в Telegram "
                         f"(обмеження {size_limit/(1024*1024):.0f}MB). "
                         f"Будь ласка, завантажте його безпосередньо з Jira.</i>")
            return await send_telegram_message(chat_id, warning_msg)
        
        # Send using the existing send_telegram_message function
        return await send_telegram_message(chat_id, message, (filename, file_bytes, mime_type))
    
    except Exception as e:
        logger.error(f"Error in send_attachment_to_telegram: {str(e)}", exc_info=True)
        return False

async def process_attachments(attachments: List[Dict[str, Any]], issue_key: str, chat_id: str) -> None:
    """
    Process and send attachment files from Jira to Telegram.
    This function delegates to the new attachment_processor utilities.
    
    Args:
        attachments: List of attachment objects from Jira
        issue_key: The issue key (e.g., 'SD-40461')
        chat_id: Telegram chat ID to send files to
    """
    try:
        if not attachments:
            logger.info("No attachments to process")
            return
            
        logger.info(f"Processing {len(attachments)} attachments for issue {issue_key}")
        
        # Add chat_id to each attachment for use by the processor
        for att in attachments:
            att['chat_id'] = chat_id
            
        # Use our new utilities to process attachments
        success, errors = await process_attachments_for_issue(
            JIRA_DOMAIN,
            attachments,
            issue_key,
            send_attachment_to_telegram
        )
        
        logger.info(f"Completed processing attachments: {success} successful, {errors} failed")
        
    except Exception as e:
        logger.error(f"Error in process_attachments: {str(e)}", exc_info=True)

def extract_embedded_attachments(text: str) -> List[dict]:
    """
    Extracts information about embedded attachments from Jira comment text.
    Processes syntax like !filename.ext|data-attachment-id=123! and other variations.
    
    Args:
        text: The comment text to analyze
        
    Returns:
        List[dict]: List of dictionaries with attachment info
    """
    import re
    import urllib.parse
    
    if not text:
        return []
        
    attachments = []
    
    # Extract embedded files using regex
    embedded_files = re.finditer(r'!([^|!]+)(?:\|([^!]+))?!', text)
    
    for file_match in embedded_files:
        # Get file name and parameters
        filename = file_match.group(1).split('/')[-1]
        clean_filename = urllib.parse.unquote(filename)
        
        # Initialize attachment info
        attachment_info = {
            'filename': clean_filename,
            'embedded': True
        }
        
        # Extract attachment ID from parameters if any
        attachment_id = None
        if file_match.group(2):  # If there are parameters
            params = file_match.group(2).strip('|').split(',')
            for param in params:
                if '=' in param:
                    key, value = param.split('=', 1)
                    value = value.strip('"')
                    
                    if key == 'data-attachment-id':
                        attachment_id = value
                        attachment_info['id'] = value
                    elif key == 'alt':
                        if value:
                            attachment_info['alt'] = value
        
        # Form the URL for downloading
        if attachment_id:
            jira_url = f"{JIRA_DOMAIN}/secure/attachment/{attachment_id}/{urllib.parse.quote(clean_filename)}"
        else:
            jira_url = f"{JIRA_DOMAIN}/secure/attachment/{urllib.parse.quote(clean_filename)}"
            
        if not jira_url.startswith(('http://', 'https://')):
            jira_url = f"https://{jira_url}"
            
        attachment_info['content'] = jira_url
        
        # Infer MIME type from extension
        attachment_info['mimeType'] = _infer_mime_type(clean_filename)
        
        attachments.append(attachment_info)
    
    return attachments

def _infer_mime_type(filename: str) -> str:
    """Helper function to infer MIME type from filename extension"""
    if filename.lower().endswith(('.jpg', '.jpeg')):
        return 'image/jpeg'
    elif filename.lower().endswith('.png'):
        return 'image/png'
    elif filename.lower().endswith('.gif'):
        return 'image/gif'
    elif filename.lower().endswith('.pdf'):
        return 'application/pdf'
    elif filename.lower().endswith(('.mp4', '.avi', '.mov')):
        return 'video/mp4'
    elif filename.lower().endswith(('.mp3', '.wav')):
        return 'audio/mpeg'
    elif filename.lower().endswith(('.doc', '.docx')):
        return 'application/msword'
    elif filename.lower().endswith('.txt'):
        return 'text/plain'
    else:
        return 'application/octet-stream'
