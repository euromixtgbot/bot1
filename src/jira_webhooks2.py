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
import sys
import os

# Add the parent directory to the path to find config
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from config.config import (
    JIRA_DOMAIN, JIRA_API_TOKEN, JIRA_EMAIL, JIRA_REPORTER_ACCOUNT_ID, TELEGRAM_TOKEN,
    WEBHOOK_RATE_LIMIT_ENABLED, WEBHOOK_RATE_LIMIT_MAX_REQUESTS, WEBHOOK_RATE_LIMIT_WINDOW,
    WEBHOOK_RATE_LIMIT_BLACKLIST_DURATION, WEBHOOK_IP_WHITELIST_ENABLED, WEBHOOK_IP_WHITELIST_CUSTOM
)
from src.services import find_user_by_jira_issue_key
from src.fixed_issue_formatter import format_issue_info, format_issue_text
from src.jira_attachment_utils import build_attachment_urls, download_file_from_jira, normalize_jira_domain
from src.attachment_processor import process_attachments_for_issue

# Ініціалізуємо логування з ротацією для вебхуків
from logging.handlers import RotatingFileHandler
from datetime import datetime

# Створюємо окремий логер для вебхуків з ротацією
webhook_log_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
webhook_log_filename = f'logs/webhook_001_{webhook_log_timestamp}.log'

# Налаштовуємо ротуючий файловий хендлер для вебхуків (5MB максимум, 10 файлів)
webhook_rotating_handler = RotatingFileHandler(
    webhook_log_filename,
    maxBytes=5*1024*1024,  # 5MB
    backupCount=10,        # Зберігати до 10 файлів
    encoding='utf-8'
)

# Налаштовуємо форматування для вебхук логів
webhook_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
webhook_rotating_handler.setFormatter(webhook_formatter)

# Створюємо logger для вебхуків
logger = logging.getLogger(__name__)
logger.addHandler(webhook_rotating_handler)
logger.setLevel(logging.INFO)

# === Константи ===
# Типи подій, на які реагуємо
EVENT_ISSUE_UPDATED = "jira:issue_updated"
EVENT_COMMENT_CREATED = "comment_created"
EVENT_ISSUE_CREATED = "jira:issue_created"
EVENT_ATTACHMENT_CREATED = "attachment_created"

# === SECURITY: Rate Limiting and IP Whitelist ===
# Rate limiting: максимум запитів з одного IP за вікно часу
RATE_LIMIT_WINDOW = WEBHOOK_RATE_LIMIT_WINDOW  # секунд (з config)
RATE_LIMIT_MAX_REQUESTS = WEBHOOK_RATE_LIMIT_MAX_REQUESTS  # максимум запитів за вікно (з config)
RATE_LIMIT_BLACKLIST_DURATION = WEBHOOK_RATE_LIMIT_BLACKLIST_DURATION  # тривалість блокування (з config)

# IP Whitelist: дозволені IP-адреси для webhook запитів
# Jira Cloud IP ranges (оновлено станом на 2025)
IP_WHITELIST = {
    # Localhost для тестування
    "127.0.0.1",
    "::1",
    
    # Jira Cloud IP ranges (Atlassian)
    # https://support.atlassian.com/organization-administration/docs/ip-addresses-and-domains-for-atlassian-cloud-products/
    "13.52.5.0/24",
    "13.236.8.0/21",
    "18.136.0.0/16",
    "18.184.0.0/16",
    "18.234.32.0/20",
    "18.246.0.0/16",
    "52.215.192.0/21",
    "104.192.136.0/21",
    "185.166.140.0/22",
    "185.166.142.0/23",
    "185.166.143.0/24",
    
    # Внутрішня мережа (якщо потрібно)
    "192.168.0.0/16",
    "10.0.0.0/8",
}

# Додаємо custom IP з config
if WEBHOOK_IP_WHITELIST_CUSTOM:
    for ip in WEBHOOK_IP_WHITELIST_CUSTOM.split(','):
        ip = ip.strip()
        if ip:
            IP_WHITELIST.add(ip)
            logger.info(f"✅ Added custom IP to whitelist from config: {ip}")

# Глобальні структури для rate limiting
from collections import deque
RATE_LIMIT_TRACKER: Dict[str, deque] = defaultdict(lambda: deque(maxlen=RATE_LIMIT_MAX_REQUESTS))
RATE_LIMIT_BLACKLIST: Dict[str, float] = {}  # {ip: blacklist_until_timestamp}

def is_ip_in_whitelist(ip: str) -> bool:
    """
    Перевіряє чи IP-адреса в whitelist (включаючи підмережі CIDR).
    
    Args:
        ip: IP-адреса для перевірки
        
    Returns:
        bool: True якщо IP дозволений
    """
    from ipaddress import ip_address, ip_network
    
    try:
        ip_obj = ip_address(ip)
        for allowed in IP_WHITELIST:
            if '/' in allowed:
                # CIDR notation
                if ip_obj in ip_network(allowed, strict=False):
                    return True
            else:
                # Exact IP match
                if str(ip_obj) == allowed:
                    return True
        return False
    except ValueError:
        logger.warning(f"Invalid IP address format: {ip}")
        return False

def check_rate_limit(ip: str) -> Tuple[bool, str]:
    """
    Перевіряє rate limit для IP-адреси.
    
    Args:
        ip: IP-адреса для перевірки
        
    Returns:
        Tuple[bool, str]: (дозволений, причина блокування)
    """
    current_time = time.time()
    
    # Перевірка чи IP в чорному списку
    if ip in RATE_LIMIT_BLACKLIST:
        blacklist_until = RATE_LIMIT_BLACKLIST[ip]
        if current_time < blacklist_until:
            remaining = int(blacklist_until - current_time)
            return False, f"IP blacklisted for {remaining}s (rate limit exceeded)"
        else:
            # Час блокування закінчився
            del RATE_LIMIT_BLACKLIST[ip]
            RATE_LIMIT_TRACKER[ip].clear()
    
    # Отримуємо історію запитів для цього IP
    request_times = RATE_LIMIT_TRACKER[ip]
    
    # Видаляємо старі запити (поза вікном)
    while request_times and request_times[0] < current_time - RATE_LIMIT_WINDOW:
        request_times.popleft()
    
    # Перевіряємо ліміт
    if len(request_times) >= RATE_LIMIT_MAX_REQUESTS:
        # Перевищено ліміт - додаємо в чорний список
        RATE_LIMIT_BLACKLIST[ip] = current_time + RATE_LIMIT_BLACKLIST_DURATION
        logger.warning(f"🚫 Rate limit exceeded for IP {ip}: {len(request_times)} requests in {RATE_LIMIT_WINDOW}s. Blacklisted for {RATE_LIMIT_BLACKLIST_DURATION}s")
        return False, f"Rate limit exceeded: {len(request_times)}/{RATE_LIMIT_MAX_REQUESTS} requests per {RATE_LIMIT_WINDOW}s"
    
    # Додаємо поточний запит
    request_times.append(current_time)
    return True, ""

@web.middleware
async def security_middleware(request: web.Request, handler) -> web.Response:
    """
    Middleware для перевірки безпеки запитів (IP whitelist, rate limiting).
    
    Args:
        request: Вхідний запит
        handler: Наступний обробник
        
    Returns:
        web.Response: Відповідь
    """
    # Отримуємо IP-адресу клієнта
    # Враховуємо proxy (X-Forwarded-For, X-Real-IP)
    client_ip = request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
    if not client_ip:
        client_ip = request.headers.get('X-Real-IP', '').strip()
    if not client_ip:
        client_ip = request.remote or '0.0.0.0'
    
    # Перевірка 1: IP Whitelist (якщо увімкнена)
    if WEBHOOK_IP_WHITELIST_ENABLED:
        if not is_ip_in_whitelist(client_ip):
            logger.warning(f"🚫 Blocked request from non-whitelisted IP: {client_ip} (path: {request.path})")
            return web.json_response(
                {"status": "error", "message": "Access denied"},
                status=403
            )
    
    # Перевірка 2: Rate Limiting (якщо увімкнена)
    if WEBHOOK_RATE_LIMIT_ENABLED:
        allowed, reason = check_rate_limit(client_ip)
        if not allowed:
            logger.warning(f"🚫 Blocked request from {client_ip}: {reason}")
            return web.json_response(
                {"status": "error", "message": "Too many requests"},
                status=429
            )
    
    # Запит дозволений
    return await handler(request)

def add_ip_to_whitelist(ip: str) -> bool:
    """
    Додає IP-адресу до whitelist (для адміністративного використання).
    
    Args:
        ip: IP-адреса або CIDR підмережа
        
    Returns:
        bool: True якщо успішно додано
    """
    try:
        from ipaddress import ip_address, ip_network
        
        # Валідація
        if '/' in ip:
            ip_network(ip, strict=False)  # Перевірка CIDR
        else:
            ip_address(ip)  # Перевірка IP
        
        IP_WHITELIST.add(ip)
        logger.info(f"✅ Added IP to whitelist: {ip}")
        return True
    except ValueError as e:
        logger.error(f"❌ Invalid IP format: {ip} - {e}")
        return False

def remove_ip_from_blacklist(ip: str) -> bool:
    """
    Видаляє IP-адресу з blacklist (для адміністративного використання).
    
    Args:
        ip: IP-адреса
        
    Returns:
        bool: True якщо успішно видалено
    """
    if ip in RATE_LIMIT_BLACKLIST:
        del RATE_LIMIT_BLACKLIST[ip]
        if ip in RATE_LIMIT_TRACKER:
            RATE_LIMIT_TRACKER[ip].clear()
        logger.info(f"✅ Removed IP from blacklist: {ip}")
        return True
    else:
        logger.warning(f"⚠️ IP not in blacklist: {ip}")
        return False

# Типи подій, які ми логуємо але не обробляємо
EVENT_ISSUE_PROPERTY_SET = "issue_property_set"
EVENT_ISSUELINK_CREATED = "issuelink_created"
EVENT_WORKLOG_CREATED = "worklog_created"
EVENT_WORKLOG_UPDATED = "worklog_updated"
EVENT_WORKLOG_DELETED = "worklog_deleted"
EVENT_USER_CREATED = "user_created"
EVENT_USER_UPDATED = "user_updated"

# Кеш для зберігання відправлених повідомлень, щоб уникнути дублікатів
# Структура: {issue_key: [{"text": "message_text", "time": timestamp}]]}
# Зберігаємо тільки останні повідомлення за останні 5 хвилин
RECENT_MESSAGES_CACHE: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
CACHE_TTL = 300  # 5 minutes

# ===== ATTACHMENT CACHING SYSTEM =====
# Кеш для зберігання подій attachment_created до прибуття comment_created
# Структура: {issue_key: [{"attachment": attachment_data, "timestamp": time, "filename": str}]}
PENDING_ATTACHMENTS_CACHE: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
ATTACHMENT_CACHE_TTL = 300  # 5 minutes - INCREASED for debugging timing issues

# НОВИЙ ГЛОБАЛЬНИЙ КЕШ ЗА ATTACHMENT_ID (для вкладень без issue_key)
# Структура: {attachment_id: {"attachment": data, "timestamp": time, "filename": str}}
ATTACHMENT_ID_CACHE: Dict[str, Dict[str, Any]] = {}
ATTACHMENT_ID_CACHE_TTL = 600  # 10 minutes - INCREASED for debugging

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
        elif event_type in [EVENT_ISSUE_PROPERTY_SET, EVENT_ISSUELINK_CREATED, 
                           EVENT_WORKLOG_CREATED, EVENT_WORKLOG_UPDATED, EVENT_WORKLOG_DELETED,
                           EVENT_USER_CREATED, EVENT_USER_UPDATED]:
            # Логуємо інформаційні події без обробки
            logger.info(f"ℹ️ Info event received: {event_type} - logging only, no action taken")
            issue_key = webhook_data.get('issue', {}).get('key', 'N/A')
            if issue_key != 'N/A':
                logger.info(f"   Issue: {issue_key}")
            return web.json_response({"status": "success", "message": f"Info event logged: {event_type}"})
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
        
        # Інформаційні події - завжди валідні (логуємо але не обробляємо)
        elif event_type in [EVENT_ISSUE_PROPERTY_SET, EVENT_ISSUELINK_CREATED,
                           EVENT_WORKLOG_CREATED, EVENT_WORKLOG_UPDATED, EVENT_WORKLOG_DELETED,
                           EVENT_USER_CREATED, EVENT_USER_UPDATED]:
            return True
            
        return False
        
    except Exception as e:
        logger.error(f"Error validating webhook data: {str(e)}", exc_info=True)
        return False

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
        
        # Готуємо повідомлення про зміну статусу
        message = (
            f"📝 Статус Задачі:<b>{issue_key}</b> оновлено: <b>{new_status}</b>\n"
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
        
        # Skip comments that start with "*Ім'я:" or "**Ім'я:" - these are author headers from bot
        if comment_body and (comment_body.startswith("*Ім'я:") or comment_body.startswith("**Ім'я:")):
            logger.info(f"Skipping comment with author header: {comment_body[:50]}...")
            return
        
        # Find Telegram user
        user_data = await find_user_by_jira_issue_key(issue_key)
        if not user_data:
            logger.info(f"No Telegram user found for issue {issue_key} - issue created manually in Jira, skipping notification")
            return
            
        logger.debug(f"Found Telegram user: {user_data}")
        
        # Collect all attachments from different possible locations
        attachments = []
        
        logger.info("🔍 SEARCHING FOR ATTACHMENTS IN ALL LOCATIONS:")
        
        # КРИТИЧНЕ ВИПРАВЛЕННЯ: Збільшена затримка для завершення кешування ВСІХ файлів
        logger.info("⏳ Waiting 5 seconds for all attachment_created events to complete...")
        await asyncio.sleep(5)  # Збільшено з 2 до 5 секунд для повного завершення всіх attachment_created подій
        
        # НОВИНКА: Спочатку перевіряємо закешовані вкладення + ID-based пошук
        comment_timestamp = time.time()  # Приблизний час коментаря
        
        # Отримуємо embedded attachments для допомоги в пошуку
        embedded_attachments = []
        if comment_body:
            embedded_attachments = extract_embedded_attachments(comment_body)
            logger.info(f"📎 Found {len(embedded_attachments)} embedded attachments in comment")
            for i, att in enumerate(embedded_attachments):
                filename = att.get('filename', 'unknown')
                logger.info(f"   {i+1}. {filename}")
        
        # Використовуємо нову стратегію пошуку
        cached_attachments = find_cached_attachments_by_patterns(issue_key, embedded_attachments, comment_timestamp)
        if cached_attachments:
            logger.info(f"📦 Found {len(cached_attachments)} cached attachments via enhanced search:")
            for i, att in enumerate(cached_attachments):
                filename = att.get('filename', 'unknown')
                att_id = att.get('id', 'no-id')
                logger.info(f"   🎯 CACHED {i+1}. {filename} (ID: {att_id})")
            attachments.extend(cached_attachments)
            
            # КРИТИЧНА ПЕРЕВІРКА: Чи всі embedded файли знайдені?
            if embedded_attachments:
                found_filenames = {att.get('filename', '') for att in cached_attachments}
                embedded_filenames = {att.get('filename', '') for att in embedded_attachments}
                missing_files = embedded_filenames - found_filenames
                
                if missing_files:
                    logger.warning(f"⚠️ MISSING FILES DETECTED: {len(missing_files)} embedded files not found in cache!")
                    for missing_file in missing_files:
                        logger.warning(f"   ❌ MISSING: {missing_file}")
                    
                    # Додаткова спроба знайти через розширений пошук
                    logger.info("🔄 Attempting additional search for missing files...")
                    additional_search = find_cached_attachments_by_patterns(
                        issue_key, 
                        [{'filename': f} for f in missing_files], 
                        comment_timestamp,
                        extend_time_window=True  # Розширюємо часове вікно
                    )
                    
                    if additional_search:
                        logger.info(f"✅ RECOVERY: Found {len(additional_search)} additional files")
                        for att in additional_search:
                            logger.info(f"   ✅ RECOVERED: {att.get('filename', 'unknown')} (ID: {att.get('id', 'no-id')})")
                        attachments.extend(additional_search)
                    else:
                        logger.error(f"❌ CRITICAL: Unable to recover {len(missing_files)} missing files")
                else:
                    logger.info("✅ ALL EMBEDDED FILES FOUND in cache")
        else:
            logger.warning(f"❌ NO CACHED ATTACHMENTS FOUND with enhanced search")
        
        # 1. Direct attachments on the comment
        if 'attachment' in comment:
            direct_attachments = comment.get('attachment', [])
            logger.info(f"📎 Comment direct attachments: {len(direct_attachments)}")
            attachments.extend(direct_attachments)
            
        if 'attachments' in comment:
            plural_attachments = comment.get('attachments', [])
            logger.info(f"📎 Comment plural attachments: {len(plural_attachments)}")
            attachments.extend(plural_attachments)
            
        # 2. Issue-level attachments (CRITICAL FIX - files are often attached to issue, not comment)
        if 'issue' in webhook_data and 'fields' in webhook_data['issue']:
            issue_attachments = webhook_data['issue']['fields'].get('attachment', [])
            logger.info(f"📎 Issue-level attachments: {len(issue_attachments)}")
            if issue_attachments:
                for i, att in enumerate(issue_attachments):
                    filename = att.get('filename', 'unknown')
                    att_id = att.get('id', 'no-id')
                    logger.info(f"   {i+1}. {filename} (ID: {att_id})")
                attachments.extend(issue_attachments)
            
        # 3. Additional embedded attachments (якщо не знайдені раніше)
        if comment_body and not embedded_attachments:
            embedded = extract_embedded_attachments(comment_body)
            logger.info(f"📎 Additional embedded attachments in comment body: {len(embedded)}")
            if embedded:
                for i, att in enumerate(embedded):
                    filename = att.get('filename', 'unknown')
                    att_id = att.get('id', 'no-id')
                    logger.info(f"   {i+1}. {filename} (ID: {att_id})")
                logger.debug(f"Additional embedded attachments: {json.dumps(embedded, indent=2)}")
                attachments.extend(embedded)
                
        # 4. Special content structure (some Jira versions)
        if 'content' in comment:
            content = comment.get('content', [])
            content_attachments = []
            for item in content:
                if isinstance(item, dict) and 'attachment' in item:
                    content_attachments.append(item['attachment'])
            
            logger.info(f"📎 Content structure attachments: {len(content_attachments)}")
            if content_attachments:
                for i, att in enumerate(content_attachments):
                    filename = att.get('filename', 'unknown')
                    att_id = att.get('id', 'no-id')
                    logger.info(f"   {i+1}. {filename} (ID: {att_id})")
                    logger.debug(f"Found attachment in content structure: {json.dumps(att, indent=2)}")
                attachments.extend(content_attachments)
                    
        # 5. ВАЖЛИВО: НЕ завантажуємо всі вкладення задачі як fallback!
        # Якщо немає вкладень у коментарі, значить коментар БЕЗ вкладень
        if not attachments and issue_key:
            logger.info(f"📡 No attachments found in webhook for comment - this is normal for text-only comments")
            logger.info(f"❌ SKIPPING API fallback to prevent sending ALL issue attachments")
            # НЕ робимо API запит - це призведе до пересилання всіх вкладень задачі!
        
        # Remove duplicates by ID
        unique_attachments = []
        seen_ids = set()
        
        for att in attachments:
            att_id = att.get('id')
            if att_id and att_id not in seen_ids:
                unique_attachments.append(att)
                seen_ids.add(att_id)
            elif not att_id:  # No ID, check by filename
                filename = att.get('filename', '')
                if filename and filename not in [a.get('filename') for a in unique_attachments]:
                    unique_attachments.append(att)
        
        logger.info(f"📋 After deduplication: {len(unique_attachments)} unique attachments")
        attachments = unique_attachments
                    
        # Log attachment info
        if attachments:
            logger.info(f"🎯 TOTAL FOUND: {len(attachments)} total attachments")
            for idx, att in enumerate(attachments, 1):
                filename = att.get('filename', 'unknown')
                att_id = att.get('id', 'no-id')
                att_url = att.get('content', att.get('self', ''))
                mime_type = att.get('mimeType', att.get('contentType', 'unknown'))
                logger.info(f"📎 Attachment {idx}: {filename}")
                logger.info(f"   - ID: {att_id}")
                logger.info(f"   - MIME: {mime_type}")
                logger.info(f"   - URL: {att_url}")
                logger.debug(f"   - Full data: {json.dumps(att, indent=2)}")
        else:
            logger.warning("❌ NO ATTACHMENTS FOUND IN WEBHOOK!")
            # Log the full webhook for debugging
            logger.debug(f"Full webhook data: {json.dumps(webhook_data, indent=2, ensure_ascii=False)}")
                
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
            
        # Send main message (only if there's text content)
        message = "\n".join(message_parts)
        if message:
            await send_telegram_message(user_data['telegram_id'], message)
            
        # Process and send attachments
        if attachments:
            logger.info("Starting to process attachments")
            #await process_attachments(attachments, issue_key, user_data['telegram_id'])
            await process_attachments_universal(attachments, issue_key, user_data['telegram_id'])
        
        # Очищаємо кеш вкладень після обробки коментаря  
        cleanup_attachment_cache()
            
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
            f"🆕 <b>Створено нову задачу:{issue_key}</b>\n\n"
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
    ЗМІНЕНО: Тепер кешує вкладення замість негайної відправки.
    Вкладення будуть відправлені при обробці comment_created події.
    """
    try:
        # Логуємо повні дані вебхука для відлагодження
        logger.info(f"🔔 ATTACHMENT_CREATED EVENT RECEIVED")
        logger.debug(f"Отримано подію attachment_created: {json.dumps(webhook_data, indent=2)}")
        
        # Отримуємо дані про вкладення
        attachment = webhook_data.get('attachment', {})
        if isinstance(attachment, list):
            attachment = attachment[0] if attachment else {}
        if not attachment:
            logger.warning("Отримано подію attachment_created без даних вкладення")
            return
            
        attachment_id = attachment.get('id', '')
        filename = attachment.get('filename', 'unknown_file')
        
        logger.info(f"📎 Processing attachment_created: {filename} (ID: {attachment_id})")
        
        # Отримуємо issue_key для кешування
        issue_key = None
        
        # Спочатку шукаємо ключ задачі в даних вебхука
        if 'issue' in webhook_data:
            issue = webhook_data.get('issue', {})
            issue_key = issue.get('key', '')
            logger.info(f"✅ Found issue key in webhook data: {issue_key}")
        
        # НОВИЙ FALLBACK: Якщо немає issue в webhook, спробуємо через issueId
        if not issue_key and 'issueId' in webhook_data:
            issue_id = webhook_data.get('issueId', '')
            logger.info(f"🔍 Found issueId in webhook, will try to resolve: {issue_id}")
            # issueId зазвичай не містить ключ, але може бути корисним для API запитів
            
        # НОВИЙ FALLBACK: Перевіримо attachment дані на наявність issue посилань
        if not issue_key and attachment:
            for url_field in ['self', 'content', 'url']:
                url = attachment.get(url_field, '')
                if url and '/issue/' in url:
                    # Спробувати витягнути issue key з URL
                    match = re.search(r'/issue/([A-Z]+-\d+)', url)
                    if match:
                        issue_key = match.group(1)
                        logger.info(f"✅ Extracted issue key from attachment URL: {issue_key}")
                        break
        
        # Якщо немає ключа в webhook, намагаємося отримати через API
        if not issue_key and attachment_id:
            logger.info(f"🌐 No issue key in webhook, trying API for attachment {attachment_id}")
            issue_key = await get_issue_key_from_attachment_api(attachment_id)
        
        # Якщо все ще немає ключа, намагаємося витягнути з URL
        if not issue_key:
            logger.info(f"🔍 Trying to extract issue key from attachment URLs")
            issue_key = extract_issue_key_from_urls(attachment)
        
        if not issue_key:
            logger.warning(f"❌ Cannot determine issue key for attachment {attachment_id}. Using ID-based caching.")
            logger.debug(f"Available webhook data fields: {list(webhook_data.keys())}")
            logger.debug(f"Attachment data: {json.dumps(attachment, indent=2)}")
            
            # FALLBACK: Кешуємо за attachment_id
            add_attachment_to_id_cache(attachment)
            logger.info(f"💡 Attachment {filename} cached by ID. Will be matched later by filename/timestamp.")
            
            # Очищаємо старі записи з кешу
            cleanup_attachment_cache()
            return
        
        # ОСНОВНА ЗМІНА: Кешуємо вкладення замість негайної відправки
        logger.info(f"🔵 ATTEMPTING TO CACHE: {filename} for issue {issue_key}")
        logger.info(f"🔵 CACHE STATE BEFORE: {len(PENDING_ATTACHMENTS_CACHE)} issues, {sum(len(v) for v in PENDING_ATTACHMENTS_CACHE.values())} total attachments")
        
        add_attachment_to_cache(issue_key, attachment)
        
        logger.info(f"🔵 CACHE STATE AFTER: {len(PENDING_ATTACHMENTS_CACHE)} issues, {sum(len(v) for v in PENDING_ATTACHMENTS_CACHE.values())} total attachments")
        logger.info(f"✅ Attachment {filename} cached for issue {issue_key}")
        logger.info(f"💡 Waiting for comment_created event to process attachment...")
        
        # Очищаємо старі записи з кешу
        cleanup_attachment_cache()
        
    except Exception as e:
        logger.error(f"❌ Error in handle_attachment_created: {str(e)}", exc_info=True)

async def get_issue_key_from_attachment_api(attachment_id: str) -> Optional[str]:
    """
    Отримує issue_key через REST API за attachment_id.
    
    Args:
        attachment_id: ID вкладення
        
    Returns:
        str|None: Ключ задачі або None якщо не знайдено
    """
    if not attachment_id:
        logger.warning("Empty attachment_id provided to get_issue_key_from_attachment_api")
        return None
        
    max_retries = 2  # Зменшено для швидшості
    base_retry_delay = 0.5  # Швидші retry
    
    # КРИТИЧНЕ ВИПРАВЛЕННЯ: Нормалізуємо домен щоб уникнути подвійного https://
    from src.jira_attachment_utils import normalize_jira_domain
    domain = normalize_jira_domain(JIRA_DOMAIN)
    api_url = f"https://{domain}/rest/api/3/attachment/{attachment_id}"
    
    auth = httpx.BasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
    headers = {
        'X-Atlassian-Token': 'no-check',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Connection': 'keep-alive'
    }
    
    logger.info(f"🌐 Attempting API call: {api_url}")
    
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(
                timeout=15.0,  # Коротший timeout
                auth=auth,
                verify=True,
                trust_env=True
            ) as client:
                response = await client.get(api_url, headers=headers)
                
                if response.status_code == 404:
                    logger.warning(f"Attachment {attachment_id} not found (404)")
                    return None
                    
                response.raise_for_status()
                attachment_info = response.json()
                
                logger.debug(f"API Response: {json.dumps(attachment_info, indent=2)}")
                
                # В різних версіях Jira може бути різне поле
                for field in ['issueId', 'issueKey', 'issue']:
                    if field in attachment_info:
                        value = attachment_info[field]
                        if isinstance(value, dict):
                            issue_key = value.get('key', '')
                        else:
                            issue_key = str(value)
                        if issue_key and re.match(r'^[A-Z]+-\d+$', issue_key):
                            logger.info(f"🔍 Found issue key via API: {issue_key}")
                            return issue_key
                
                logger.warning(f"No valid issue key found in API response for attachment {attachment_id}")
                return None
                
        except httpx.ConnectError as conn_error:
            logger.warning(f"Connection error (attempt {attempt + 1}/{max_retries}): {str(conn_error)}")
            if attempt < max_retries - 1:
                retry_delay = base_retry_delay * (2 ** attempt)
                logger.info(f"Waiting {retry_delay} seconds before retry...")
                await asyncio.sleep(retry_delay)
                continue
        except httpx.HTTPError as http_error:
            logger.warning(f"HTTP error (attempt {attempt + 1}/{max_retries}): {str(http_error)}")
            if attempt < max_retries - 1:
                retry_delay = base_retry_delay * (2 ** attempt)
                await asyncio.sleep(retry_delay)
                continue
        except Exception as e:
            logger.error(f"Unexpected error accessing Jira API: {str(e)}")
            break
    
    logger.error(f"Failed to get issue key for attachment {attachment_id} after {max_retries} attempts")
    return None

def extract_issue_key_from_urls(attachment: Dict[str, Any]) -> Optional[str]:
    """
    Витягує issue_key з URL вкладення.
    
    Args:
        attachment: Дані вкладення
        
    Returns:
        str|None: Ключ задачі або None якщо не знайдено  
    """
    urls_to_check = set()
    
    # Збираємо всі можливі URL
    for field in ['self', 'content', 'url']:
        url = attachment.get(field)
        if url:
            urls_to_check.add(url)
    
    # Додаємо додаткові URL
    attachment_id = attachment.get('id', '')
    if attachment_id:
        # ВИПРАВЛЕННЯ: Нормалізуємо домен
        from src.jira_attachment_utils import normalize_jira_domain
        domain = normalize_jira_domain(JIRA_DOMAIN)
        urls_to_check.add(f"https://{domain}/secure/attachment/{attachment_id}")
        urls_to_check.add(f"https://{domain}/rest/api/3/attachment/{attachment_id}")
    
    patterns = [
        r'/issue/([^/]+)/attachment',
        r'/([A-Z]+-\d+)/attachments',
        r'/secure/attachment/[0-9a-f-]+/([A-Z]+-\d+)',
        r'/projects/[^/]+/issues/([^/]+)',
        r'/([A-Z]+-\d+)/content',
        r'selectedIssue=([A-Z]+-\d+)',
        r'issueKey=([A-Z]+-\d+)'
    ]
    
    for url in urls_to_check:
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                found_key = match.group(1)
                if re.match(r'^[A-Z]+-\d+$', found_key):
                    logger.info(f"🔍 Extracted issue key from URL: {found_key}")
                    return found_key
    
    return None

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

async def send_file_as_separate_message(chat_id: str, filename: str, file_content: bytes, mime_type: str, issue_key: str) -> bool:
    """
    Універсальна функція для відправки файлів як окремих повідомлень в Telegram.
    Автоматично вибирає найкращий метод API в залежності від типу файлу.
    
    Args:
        chat_id: ID чату в Telegram
        filename: Ім'я файлу
        file_content: Вміст файлу в байтах
        mime_type: MIME тип файлу
        issue_key: Ключ задачі Jira
        
    Returns:
        bool: True якщо файл успішно відправлено
    """
    try:
        if not file_content:
            logger.error(f"Empty file content for {filename}")
            return False
            
        file_size = len(file_content)
        file_size_mb = file_size / (1024 * 1024)
        
        # Визначаємо тип файлу та іконку
        if mime_type.startswith('image/'):
            file_type_icon = "🖼️"
            file_type_name = "Зображення"
            telegram_method = "sendPhoto"
            size_limit = 10 * 1024 * 1024  # 10MB for photos
        elif mime_type.startswith('video/'):
            file_type_icon = "🎥"
            file_type_name = "Відео"
            telegram_method = "sendVideo" 
            size_limit = 50 * 1024 * 1024  # 50MB for videos
        elif mime_type.startswith('audio/'):
            file_type_icon = "🎵"
            file_type_name = "Аудіо"
            telegram_method = "sendAudio"
            size_limit = 50 * 1024 * 1024  # 50MB for audio
        elif mime_type == 'application/vnd.ms-excel' or mime_type == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
            file_type_icon = "📊"
            file_type_name = "Excel документ"
            telegram_method = "sendDocument"
            size_limit = 50 * 1024 * 1024  # 50MB for documents
        elif mime_type == 'application/pdf':
            file_type_icon = "📄"
            file_type_name = "PDF документ"
            telegram_method = "sendDocument"
            size_limit = 50 * 1024 * 1024
        elif mime_type.startswith('text/'):
            file_type_icon = "📝"
            file_type_name = "Текстовий файл"
            telegram_method = "sendDocument"
            size_limit = 50 * 1024 * 1024
        else:
            file_type_icon = "📎"
            file_type_name = "Документ"
            telegram_method = "sendDocument"
            size_limit = 50 * 1024 * 1024
            
        # Формуємо повідомлення (simplified without tech support header)
        message = f"{file_type_icon} <b>{filename}</b> ({file_size_mb:.1f} MB)"
        
        # Перевіряємо розмір файлу
        if file_size > size_limit:
            warning_msg = (f"{message}\n\n⚠️ <i>Файл завеликий для надсилання в Telegram "
                         f"(обмеження {size_limit/(1024*1024):.0f}MB). "
                         f"Будь ласка, завантажте його безпосередньо з Jira.</i>")
            return await send_telegram_message(chat_id, warning_msg)
        
        logger.info(f"📤 Sending {file_type_name.lower()} via {telegram_method}: {filename} ({file_size_mb:.1f}MB)")
        
        # Відправляємо файл через наявну функцію
        return await send_telegram_message(chat_id, message, (filename, file_content, mime_type))
        
    except Exception as e:
        logger.error(f"Error in send_file_as_separate_message for {filename}: {str(e)}", exc_info=True)
        return False

async def process_attachments_universal(attachments: List[Dict[str, Any]], issue_key: str, chat_id: str) -> None:
    """
    Універсальна обробка вкладень з кешованими та webhook даними.
    Об'єднує кешовані вкладення з отриманими через webhook, видаляє дублікати 
    та відправляє кожен файл як окреме повідомлення.
    
    Args:
        attachments: Список вкладень з webhook
        issue_key: Ключ задачі Jira
        chat_id: ID чату в Telegram
    """
    try:
        logger.info(f"🔄 Starting universal attachment processing for issue {issue_key}")
        
        # Об'єднуємо вкладення з різних джерел
        all_attachments = []
        
        # Додаємо кешовані вкладення (вже отримані через get_cached_attachments)
        if attachments:
            logger.info(f"📥 Processing {len(attachments)} attachments from webhook/cache")
            all_attachments.extend(attachments)
        
        # Видаляємо дублікати за ID та ім'ям файлу
        unique_attachments = []
        seen_ids = set()
        seen_filenames = set()
        
        for att in all_attachments:
            att_id = att.get('id')
            filename = att.get('filename', '')
            
            # Перевірка на дублікати за ID
            if att_id and att_id in seen_ids:
                logger.debug(f"🔄 Skipping duplicate attachment by ID: {filename} (ID: {att_id})")
                continue
                
            # Перевірка на дублікати за ім'ям файлу
            if filename and filename in seen_filenames:
                logger.debug(f"🔄 Skipping duplicate attachment by filename: {filename}")
                continue
                
            # Додаємо до унікальних
            unique_attachments.append(att)
            if att_id:
                seen_ids.add(att_id)
            if filename:
                seen_filenames.add(filename)
        
        logger.info(f"✅ After deduplication: {len(unique_attachments)} unique attachments")
        
        if not unique_attachments:
            logger.info("ℹ️ No attachments to process")
            return
        
        # Обробляємо кожен файл окремо
        success_count = 0
        error_count = 0
        
        for idx, attachment in enumerate(unique_attachments, 1):
            filename = attachment.get('filename', f'attachment_{idx}')
            att_id = attachment.get('id', 'unknown')
            
            logger.info(f"📎 Processing attachment {idx}/{len(unique_attachments)}: {filename} (ID: {att_id})")
            
            try:
                # Використовуємо callback функцію для обробки
                result = await send_file_as_separate_message_callback({
                    'attachment': attachment,
                    'issue_key': issue_key,
                    'chat_id': chat_id
                })
                
                if result:
                    success_count += 1
                    logger.info(f"✅ Successfully sent: {filename}")
                else:
                    error_count += 1
                    logger.error(f"❌ Failed to send: {filename}")
                    
            except Exception as e:
                error_count += 1
                logger.error(f"❌ Error processing attachment {filename}: {str(e)}", exc_info=True)
        
        logger.info(f"🏁 Attachment processing complete: {success_count} successful, {error_count} failed")
        
    except Exception as e:
        logger.error(f"❌ Error in process_attachments_universal: {str(e)}", exc_info=True)

async def send_file_as_separate_message_callback(data: Dict[str, Any]) -> bool:
    """
    Callback функція для відправки вкладень через attachment_processor.
    Адаптує дані для використання з send_file_as_separate_message.
    
    Args:
        data: Словник з ключами:
            - attachment: дані вкладення
            - issue_key: ключ задачі
            - chat_id: ID чату
            
    Returns:
        bool: True якщо файл успішно відправлено
    """
    try:
        attachment = data.get('attachment', {})
        issue_key = data.get('issue_key', '')
        chat_id = data.get('chat_id', '')
        
        if not attachment or not issue_key or not chat_id:
            logger.error("Missing required data in send_file_as_separate_message_callback")
            return False
        
        # Завантажуємо файл з Jira
        filename = attachment.get('filename', 'unknown_file')
        
        logger.info(f"⬇️ Downloading file from Jira: {filename}")
        
        # Формуємо URL для завантаження
        att_id = attachment.get('id', '')
        content_url = attachment.get('content', attachment.get('self', ''))
        urls = build_attachment_urls(JIRA_DOMAIN, att_id, filename, content_url)
        
        # Використовуємо наявну функцію для завантаження
        file_content = await download_file_from_jira(urls)
        
        if not file_content:
            logger.error(f"Failed to download file content for {filename}")
            return False
        
        # Визначаємо MIME тип
        mime_type = attachment.get('mimeType', attachment.get('contentType', _infer_mime_type(filename)))
        
        logger.info(f"📤 File downloaded ({len(file_content)} bytes), sending to Telegram...")
        
        # Відправляємо файл
        return await send_file_as_separate_message(
            chat_id=chat_id,
            filename=filename,
            file_content=file_content,
            mime_type=mime_type,
            issue_key=issue_key
        )
        
    except Exception as e:
        logger.error(f"Error in send_file_as_separate_message_callback: {str(e)}", exc_info=True)
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
    
    Args:
        text: Вихідний текст коментаря
        
    Returns:
        str: Відформатований текст
    """
    if not text:
        return text
    
    # Очищаємо Jira markup для зображень
    # Формат: !filename.ext|параметри!
    import re
    
    # Видаляємо розмітку зображень !image.jpg|width=719,height=1280,alt="image.jpg"!
    text = re.sub(r'!([^|]+\.[a-zA-Z0-9]+)(\|[^!]+)?!', '', text)
    
    # Видаляємо посилання на файли у форматі [^filename.ext]
    text = re.sub(r'\[\^[^\]]+\]', '', text)
    
    # Видаляємо зайві пробіли та порожні рядки
    text = re.sub(r'\n\s*\n', '\n', text)  # Замінюємо кілька порожніх рядків на один
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

def add_attachment_to_cache(issue_key: str, attachment: Dict[str, Any]) -> None:
    """
    Додає вкладення до кешу для подальшого зв'язування з коментарем.
    
    Args:
        issue_key: Ключ задачі  
        attachment: Дані вкладення з attachment_created події
    """
    filename = attachment.get('filename', 'unknown')
    attachment_id = attachment.get('id', 'no-id')
    
    logger.info(f"📦 CACHING: {filename} for issue {issue_key} (ID: {attachment_id})")
    logger.info(f"📦 CACHE STATE BEFORE: {len(PENDING_ATTACHMENTS_CACHE)} issues, {sum(len(v) for v in PENDING_ATTACHMENTS_CACHE.values())} total attachments")
    
    cache_entry = {
        "attachment": attachment,
        "timestamp": time.time(),
        "filename": filename,
        "attachment_id": attachment_id
    }
    
    PENDING_ATTACHMENTS_CACHE[issue_key].append(cache_entry)
    
    logger.info(f"✅ CACHED SUCCESSFULLY: Issue {issue_key} now has {len(PENDING_ATTACHMENTS_CACHE[issue_key])} cached attachments")
    logger.info(f"📦 CACHE STATE AFTER: {len(PENDING_ATTACHMENTS_CACHE)} issues, {sum(len(v) for v in PENDING_ATTACHMENTS_CACHE.values())} total attachments")
    
    # Детальний вивід для відлагодження
    for cached_issue, cached_items in PENDING_ATTACHMENTS_CACHE.items():
        logger.info(f"   📁 Issue {cached_issue}: {len(cached_items)} attachments")
        for i, item in enumerate(cached_items):
            logger.info(f"      {i+1}. {item.get('filename', 'unknown')} (ID: {item.get('attachment_id', 'no-id')})")

def get_cached_attachments(issue_key: str) -> List[Dict[str, Any]]:
    """
    Отримує всі закешовані вкладення для задачі і очищає кеш.
    
    Args:
        issue_key: Ключ задачі
        
    Returns:
        List[Dict]: Список закешованих вкладень
    """
    logger.info(f"🔍 SEARCHING CACHE for issue {issue_key}")
    logger.info(f"🔍 TOTAL CACHE STATE: {len(PENDING_ATTACHMENTS_CACHE)} issues cached")
    
    # Детальний вивід поточного стану кешу
    for cached_issue, cached_items in PENDING_ATTACHMENTS_CACHE.items():
        logger.info(f"   📁 Cached issue {cached_issue}: {len(cached_items)} attachments")
        for i, item in enumerate(cached_items):
            logger.info(f"      {i+1}. {item.get('filename', 'unknown')} (ID: {item.get('attachment_id', 'no-id')})")
    
    if issue_key not in PENDING_ATTACHMENTS_CACHE:
        logger.warning(f"❌ ISSUE KEY NOT FOUND IN CACHE: {issue_key}")
        logger.warning(f"❌ Available keys in cache: {list(PENDING_ATTACHMENTS_CACHE.keys())}")
        return []
    
    cached_attachments = PENDING_ATTACHMENTS_CACHE[issue_key]
    
    logger.info(f"✅ FOUND {len(cached_attachments)} cached attachments for issue {issue_key}")
    for item in cached_attachments:
        logger.info(f"   📎 Found: {item['filename']} (ID: {item.get('attachment_id', 'no-id')})")
    
    # Очищаємо кеш після отримання
    del PENDING_ATTACHMENTS_CACHE[issue_key]
    
    # Повертаємо тільки дані вкладень
    attachments = [item["attachment"] for item in cached_attachments]
    
    logger.info(f"📤 RETURNING {len(attachments)} attachments to process")
    return attachments

def cleanup_attachment_cache() -> None:
    """Видаляє старі вкладення з кешу."""
    current_time = time.time()
    
    # Очищаємо основний кеш за issue_key
    for issue_key in list(PENDING_ATTACHMENTS_CACHE.keys()):
        # Відфільтровуємо тільки актуальні вкладення
        recent_attachments = [
            att for att in PENDING_ATTACHMENTS_CACHE[issue_key]
            if current_time - att["timestamp"] < ATTACHMENT_CACHE_TTL
        ]
        
        if recent_attachments:
            PENDING_ATTACHMENTS_CACHE[issue_key] = recent_attachments
        else:
            # Логування для відлагодження
            old_count = len(PENDING_ATTACHMENTS_CACHE[issue_key])
            logger.warning(f"🗑️ Cleaning up {old_count} expired cached attachments for issue {issue_key}")
            del PENDING_ATTACHMENTS_CACHE[issue_key]
    
    # Очищаємо кеш за attachment_id
    expired_ids = []
    for att_id, cache_entry in ATTACHMENT_ID_CACHE.items():
        if current_time - cache_entry["timestamp"] > ATTACHMENT_ID_CACHE_TTL:
            expired_ids.append(att_id)
    
    for att_id in expired_ids:
        filename = ATTACHMENT_ID_CACHE[att_id].get("filename", "unknown")
        logger.warning(f"🗑️ Cleaning up expired attachment cache for ID {att_id}: {filename}")
        del ATTACHMENT_ID_CACHE[att_id]

def add_attachment_to_id_cache(attachment: Dict[str, Any]) -> None:
    """
    Додає вкладення до кешу за attachment_id (коли issue_key невідомий).
    
    Args:
        attachment: Дані вкладення з attachment_created події
    """
    attachment_id = attachment.get('id', '')
    filename = attachment.get('filename', 'unknown')
    
    if not attachment_id:
        logger.warning(f"Cannot cache attachment without ID: {filename}")
        return
    
    logger.info(f"🆔 Caching attachment by ID: {attachment_id} -> {filename}")
    
    ATTACHMENT_ID_CACHE[attachment_id] = {
        "attachment": attachment,
        "timestamp": time.time(),
        "filename": filename,
        "attachment_id": attachment_id
    }
    
    logger.info(f"🆔 ID-CACHE STATE: {len(ATTACHMENT_ID_CACHE)} attachments cached by ID")

def find_cached_attachments_by_patterns(issue_key: str, embedded_attachments: List[Dict[str, Any]], comment_timestamp: float, extend_time_window: bool = False) -> List[Dict[str, Any]]:
    """
    Знаходить закешовані вкладення за різними патернами зіставлення.
    
    Args:
        issue_key: Ключ задачі
        embedded_attachments: Вкладення знайдені в тексті коментаря
        comment_timestamp: Час створення коментаря
        extend_time_window: Розширити часове вікно для пошуку втрачених файлів
        
    Returns:
        List[Dict]: Список знайдених вкладень
    """
    found_attachments = []
    
    logger.info(f"🔍 SEARCHING FOR CACHED ATTACHMENTS using multiple strategies")
    logger.info(f"   - Issue key: {issue_key}")
    logger.info(f"   - Embedded attachments: {len(embedded_attachments)}")
    logger.info(f"   - Comment timestamp: {comment_timestamp}")
    logger.info(f"   - ID cache size: {len(ATTACHMENT_ID_CACHE)}")
    
    # Стратегія 1: Пошук за issue_key (як раніше)
    direct_cached = get_cached_attachments(issue_key)
    if direct_cached:
        logger.info(f"✅ STRATEGY 1: Found {len(direct_cached)} attachments via issue_key cache")
        found_attachments.extend(direct_cached)
    else:
        logger.info(f"❌ STRATEGY 1: No attachments found via issue_key cache")
    
    # Стратегія 2: Пошук за іменами файлів з embedded attachments
    embedded_filenames = {att.get('filename', '') for att in embedded_attachments if att.get('filename')}
    if embedded_filenames:
        logger.info(f"🔍 STRATEGY 2: Searching by embedded filenames: {embedded_filenames}")
        
        for att_id, cached_data in ATTACHMENT_ID_CACHE.items():
            cached_filename = cached_data.get('filename', '')
            
            # Порівнюємо імена файлів (з урахуванням можливих відмінностей)
            for embedded_filename in embedded_filenames:
                logger.info(f"   🔍 Comparing: '{cached_filename}' vs '{embedded_filename}'")
                if files_match(cached_filename, embedded_filename):
                    # Перевіряємо, чи не додано вже цей attachment за ID
                    cached_attachment = cached_data['attachment']
                    attachment_id = cached_attachment.get('id', cached_attachment.get('attachment_id', att_id))
                    
                    is_duplicate = any(
                        att.get('id') == attachment_id or 
                        att.get('attachment_id') == attachment_id or
                        att.get('id') == att_id or
                        att.get('attachment_id') == att_id
                        for att in found_attachments
                    )
                    
                    if not is_duplicate:
                        logger.info(f"✅ MATCHED by filename: {cached_filename} ≈ {embedded_filename} (ID: {att_id})")
                        found_attachments.append(cached_attachment)
                    else:
                        logger.info(f"⚠️ SKIPPED duplicate: {cached_filename} ≈ {embedded_filename} (ID: {att_id})")
                    break
                else:
                    logger.info(f"❌ NO MATCH: '{cached_filename}' ≠ '{embedded_filename}'")
    
    # Стратегія 3: Пошук за часовими мітками (розширене вікно для recovery)
    if extend_time_window:
        time_window = 600  # 10 хвилин для розширеного пошуку втрачених файлів
        logger.info(f"🔄 EXTENDED STRATEGY 3: Searching by timestamp within {time_window}s of comment (RECOVERY MODE)")
    else:
        time_window = 180  # секунд - збільшено з 30 до 180 для обробки пакетних завантажень
        logger.info(f"🔍 STRATEGY 3: Searching by timestamp within {time_window}s of comment")
    
    for att_id, cached_data in ATTACHMENT_ID_CACHE.items():
        cached_timestamp = cached_data.get('timestamp', 0)
        time_diff = abs(comment_timestamp - cached_timestamp)
        filename = cached_data.get('filename', 'unknown')
        
        logger.info(f"   📅 Checking: {filename} (ID: {att_id}, time_diff: {time_diff:.1f}s)")
        
        if time_diff <= time_window:
            # Перевіряємо, чи не додано вже цей attachment
            cached_attachment = cached_data['attachment']
            attachment_id = cached_attachment.get('id', cached_attachment.get('attachment_id', att_id))
            
            # Перевіряємо дублікати за різними можливими ID
            is_duplicate = any(
                att.get('id') == attachment_id or 
                att.get('attachment_id') == attachment_id or
                att.get('id') == att_id or
                att.get('attachment_id') == att_id
                for att in found_attachments
            )
            
            if not is_duplicate:
                logger.info(f"✅ MATCHED by timestamp: {filename} (time_diff: {time_diff:.1f}s)")
                found_attachments.append(cached_attachment)
            else:
                logger.info(f"⚠️ SKIPPED duplicate: {filename} (time_diff: {time_diff:.1f}s)")
        else:
            logger.info(f"⏰ TOO OLD: {filename} (time_diff: {time_diff:.1f}s > {time_window}s)")
    
    logger.info(f"🎯 TOTAL FOUND via all strategies: {len(found_attachments)} attachments")
    return found_attachments

def files_match(filename1: str, filename2: str) -> bool:
    """
    Перевіряє, чи відповідають два імені файлів (з урахуванням можливих відмінностей).
    
    Args:
        filename1: Перше ім'я файлу
        filename2: Друге ім'я файлу
        
    Returns:
        bool: True якщо файли відповідають
    """
    if not filename1 or not filename2:
        return False
    
    # Пряме співпадіння
    if filename1 == filename2:
        return True
    
    # Співпадіння без урахування регістру
    if filename1.lower() == filename2.lower():
        return True
    
    # Співпадіння основної частини імені (без GUID та інших суфіксів)
    import re
    
    # Видаляємо GUID-подібні суфікси
    clean1 = re.sub(r'\s*\([a-f0-9-]{36}\)', '', filename1)
    clean2 = re.sub(r'\s*\([a-f0-9-]{36}\)', '', filename2)
    
    if clean1.lower() == clean2.lower():
        return True
    
    # Співпадіння базового імені файлу (без розширення)
    base1 = filename1.rsplit('.', 1)[0].lower()
    base2 = filename2.rsplit('.', 1)[0].lower()
    
    if base1 == base2:
        return True
    
    return False

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
    web_app = web.Application(
        client_max_size=50 * 1024 * 1024,  # 50MB limit
        middlewares=[security_middleware]  # Додаємо security middleware
    )
    
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
    
    # Додаємо endpoint для моніторингу security статусу
    async def security_status(request):
        """Endpoint для перевірки security статусу (rate limiting, blacklist)."""
        current_time = time.time()
        
        # Інформація про blacklist
        blacklisted_ips = []
        for ip, until_time in RATE_LIMIT_BLACKLIST.items():
            if until_time > current_time:
                remaining = int(until_time - current_time)
                blacklisted_ips.append({
                    "ip": ip,
                    "remaining_seconds": remaining
                })
        
        # Інформація про rate limiting
        active_ips = {}
        for ip, requests in RATE_LIMIT_TRACKER.items():
            # Видаляємо старі запити
            while requests and requests[0] < current_time - RATE_LIMIT_WINDOW:
                requests.popleft()
            if requests:
                active_ips[ip] = len(requests)
        
        return web.json_response({
            "status": "ok",
            "security": {
                "rate_limit": {
                    "window_seconds": RATE_LIMIT_WINDOW,
                    "max_requests": RATE_LIMIT_MAX_REQUESTS,
                    "blacklist_duration": RATE_LIMIT_BLACKLIST_DURATION,
                    "active_ips": active_ips,
                    "blacklisted_ips": blacklisted_ips
                },
                "ip_whitelist": {
                    "enabled": True,
                    "whitelist_size": len(IP_WHITELIST)
                }
            }
        })
    
    web_app.router.add_get('/rest/webhooks/security-status', security_status)
    
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
            
        # Prepare message text (simplified without tech support header)
        icon = "🖼️" if mime_type.startswith('image/') else "📎"
        file_size_mb = file_size / (1024 * 1024)
        file_info = f"{filename} ({file_size_mb:.1f} MB)"
        message = f"{icon} <b>{file_info}</b>"
        
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
    ext = filename.lower().split('.')[-1] if '.' in filename else ''
    
    # Images
    if ext in ['jpg', 'jpeg']:
        return 'image/jpeg'
    elif ext == 'png':
        return 'image/png'
    elif ext == 'gif':
        return 'image/gif'
    elif ext == 'bmp':
        return 'image/bmp'
    elif ext == 'webp':
        return 'image/webp'
    elif ext == 'svg':
        return 'image/svg+xml'
    elif ext == 'ico':
        return 'image/x-icon'
    
    # Videos
    elif ext == 'mp4':
        return 'video/mp4'
    elif ext == 'avi':
        return 'video/x-msvideo'
    elif ext == 'mov':
        return 'video/quicktime'
    elif ext == 'wmv':
        return 'video/x-ms-wmv'
    elif ext == 'flv':
        return 'video/x-flv'
    elif ext == 'mkv':
        return 'video/x-matroska'
    
    # Audio
    elif ext == 'mp3':
        return 'audio/mpeg'
    elif ext == 'wav':
        return 'audio/wav'
    elif ext == 'flac':
        return 'audio/flac'
    elif ext == 'aac':
        return 'audio/aac'
    elif ext == 'ogg':
        return 'audio/ogg'
    
    # Documents
    elif ext == 'pdf':
        return 'application/pdf'
    elif ext == 'doc':
        return 'application/msword'
    elif ext == 'docx':
        return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    elif ext == 'xls':
        return 'application/vnd.ms-excel'
    elif ext == 'xlsx':
        return 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    elif ext == 'ppt':
        return 'application/vnd.ms-powerpoint'
    elif ext == 'pptx':
        return 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
    elif ext == 'odt':
        return 'application/vnd.oasis.opendocument.text'
    elif ext == 'ods':
        return 'application/vnd.oasis.opendocument.spreadsheet'
    elif ext == 'odp':
        return 'application/vnd.oasis.opendocument.presentation'
    elif ext == 'rtf':
        return 'application/rtf'
    
    # Archives
    elif ext == 'zip':
        return 'application/zip'
    elif ext == 'rar':
        return 'application/x-rar-compressed'
    elif ext == '7z':
        return 'application/x-7z-compressed'
    elif ext == 'tar':
        return 'application/x-tar'
    elif ext == 'gz':
        return 'application/gzip'
    elif ext == 'bz2':
        return 'application/x-bzip2'
    
    # Text files
    elif ext == 'txt':
        return 'text/plain'
    elif ext == 'csv':
        return 'text/csv'
    elif ext == 'json':
        return 'application/json'
    elif ext == 'xml':
        return 'application/xml'
    elif ext == 'html':
        return 'text/html'
    elif ext == 'css':
        return 'text/css'
    elif ext == 'js':
        return 'application/javascript'
    
    # Programming files
    elif ext == 'py':
        return 'text/x-python'
    elif ext == 'java':
        return 'text/x-java-source'
    elif ext == 'cpp':
        return 'text/x-c++src'
    elif ext == 'c':
        return 'text/x-csrc'
    elif ext == 'php':
        return 'text/x-php'
    elif ext == 'sql':
        return 'text/x-sql'
    
    # Default for unknown types
    else:
        return 'application/octet-stream'


if __name__ == "__main__":
    try:
        logger.info("🚀 Starting Jira Webhook Handler...")
        logger.info(f"📡 Server will run on http://0.0.0.0:8080")
        
        app = web.Application()
        app.router.add_post('/webhook', handle_webhook)
        
        # Add a simple health check endpoint
        async def health_check(request):
            return web.json_response({"status": "ok", "service": "jira-webhook-handler"})
        
        app.router.add_get('/health', health_check)
        
        # Start the server
        web.run_app(app, host='0.0.0.0', port=8080)
        
    except Exception as e:
        logger.error(f"❌ Failed to start webhook server: {e}")
        import traceback
        logger.error(traceback.format_exc())
