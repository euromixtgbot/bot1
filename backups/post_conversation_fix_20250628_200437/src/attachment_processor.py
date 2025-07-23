"""
Інтегратор: приклад використання утиліт із jira_attachment_utils для обробки webhook-подій.
"""
import asyncio
import logging
import re
from .jira_attachment_utils import build_attachment_urls, download_file_from_jira

# Ініціалізуємо логування
logger = logging.getLogger(__name__)

async def process_attachments_for_issue(jira_domain: str, attachments: list[dict], issue_key: str, send_file_cb) -> tuple[int, int]:
    """
    Приходить список вкладень із Jira і callback для відправки у Telegram.
    Для кожного вкладення формуємо URL, скачиваємо file_bytes і передаємо в callback.
    
    Args:
        jira_domain: домен Jira
        attachments: список вкладень
        issue_key: ключ задачі
        send_file_cb: функція для відправки файлу в Telegram
        
    send_file_cb(expected_signature: dict): Dict має ключі:
        - chat_id: str
        - file_name: str
        - file_bytes: bytes
        - mime_type: str
        - issue_key: str
        
    Returns:
        tuple[int, int]: Count of successful and failed attachment processing
    """
    from .jira_attachment_utils import get_issue_attachments_by_filename
    
    total = len(attachments)
    success = 0
    errors = 0
    
    logger.info(f"Processing {total} attachment(s) for issue {issue_key}")
    
    for idx, att in enumerate(attachments, 1):
        # Extract attachment ID from multiple possible locations
        att_id = str(att.get('id', ''))
        if not att_id and 'self' in att:
            # Try to extract ID from self URL
            match = re.search(r'/attachment/(\d+)', att.get('self', ''))
            if match:
                att_id = match.group(1)
                logger.info(f"Extracted attachment ID from self URL: {att_id}")
                
        name = att.get('filename', '') or att.get('name', f'file_{att_id}')
        mime_type = att.get('mimeType', '') or att.get('contentType', '')
        content_url = att.get('content', '') or att.get('self', '')
        
        logger.info(f"Processing attachment {idx}/{total}: {name} (ID: {att_id})")
        
        # Спеціальна обробка для вкладень без ID (inline зображення)
        if not att_id:
            logger.info(f"Вкладення без ID, шукаємо через API задачі: {name}")
            api_attachment = await get_issue_attachments_by_filename(issue_key, name)
            if api_attachment:
                # Використовуємо дані з API
                att_id = str(api_attachment.get('id', ''))
                content_url = api_attachment.get('content', '')
                if not mime_type:
                    mime_type = api_attachment.get('mimeType', '')
                logger.info(f"Знайдено вкладення через API: {name} (ID: {att_id})")
            else:
                logger.warning(f"Не вдалося знайти вкладення {name} через API")
        
        # Формуємо все можливі URL
        urls = build_attachment_urls(jira_domain, att_id, name, content_url)
        
        # Визначаємо тип файлу, якщо не було надано
        if not mime_type:
            mime_type = _infer_mime_type(name)
        
        try:
            logger.info(f"Attempting to download attachment: {name}")
            file_bytes = await download_file_from_jira(urls)
            
            if not file_bytes:
                logger.error(f"Download returned empty content for {name}")
                errors += 1
                continue
                
            # Викликаємо callback для відправки в Telegram
            logger.info(f"Sending attachment {name} ({len(file_bytes)} bytes) to Telegram")
            await send_file_cb({
                'chat_id': att.get('chat_id', ''),
                'file_name': name,
                'file_bytes': file_bytes,
                'mime_type': mime_type,
                'issue_key': issue_key
            })
            
            success += 1
            logger.info(f"Successfully processed attachment {name}")
            
            # Невелика пауза між відправкою файлів
            if idx < total:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Error processing attachment {name}: {str(e)}", exc_info=True)
            errors += 1
            continue
    
    logger.info(f"Attachment processing complete for {issue_key}: {success} successful, {errors} failed")
    return success, errors

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
