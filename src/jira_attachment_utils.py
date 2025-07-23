"""
Утиліти для обробки і скачування вкладень з Jira.
Включає нормалізацію домену, побудову URL та універсальну функцію скачування файлів із retry.
"""
import asyncio
import logging
import httpx
from typing import Optional
from urllib.parse import quote

# Ініціалізуємо логування
logger = logging.getLogger(__name__)

async def download_file_from_jira(urls: list[str], max_retries: int = 3, timeout: int = 90) -> bytes:
    """
    Спробувати скачати байти файлу по переліку можливих URL із retry та повернути байти.
    urls: список candidate URL у порядку пріоритету.
    max_retries: скільки разів спробувати кожен URL.
    timeout: таймаут HTTP запиту в секундах.
    """
    from config.config import JIRA_EMAIL, JIRA_API_TOKEN
    
    # Use basic auth credentials
    auth = httpx.BasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
    
    async with httpx.AsyncClient(timeout=timeout, auth=auth, follow_redirects=True, trust_env=True) as client:
        for url in urls:
            # Видаляємо подвійні префікси
            clean = url.replace('https://', '').replace('http://', '')
            full = f"https://{clean}"
            logger.info(f"Trying to download from URL: {full}")
            
            for attempt in range(1, max_retries + 1):
                try:
                    logger.debug(f"Download attempt {attempt}/{max_retries} for URL: {full}")
                    resp = await client.get(
                        full,
                        headers={
                            'Accept': '*/*',
                            'User-Agent': 'JiraWebhookBot/1.0'
                        }
                    )
                    resp.raise_for_status()
                    
                    # Check content type to make sure it's not an HTML error page
                    content_type = resp.headers.get('content-type', '')
                    logger.debug(f"Response content type: {content_type}")
                    
                    if content_type.startswith('text/html'):
                        logger.warning(f"Received HTML response instead of file content. URL: {full}")
                        if attempt == max_retries:
                            break
                        await asyncio.sleep(1)
                        continue
                    
                    content = resp.content
                    if not content:
                        logger.warning("Received empty file content")
                        if attempt == max_retries:
                            break
                        await asyncio.sleep(1)
                        continue
                    
                    # Double check for small content that might be an error message
                    if len(content) < 100:  # If content is suspiciously small
                        logger.warning(f"Downloaded content is suspiciously small ({len(content)} bytes)")
                        try:
                            error_text = content.decode('utf-8')
                            if 'error' in error_text.lower() or 'unauthorized' in error_text.lower():
                                logger.warning(f"Received error message instead of file: {error_text}")
                                if attempt == max_retries:
                                    break
                                await asyncio.sleep(1)
                                continue
                        except UnicodeDecodeError:
                            # If we can't decode as text, it's probably binary data which is fine
                            pass
                    
                    logger.info(f"Successfully downloaded {len(content)} bytes")
                    return content
                    
                except httpx.HTTPError as e:
                    logger.warning(f"HTTP error while downloading from {full}: {str(e)}")
                    if attempt == max_retries:
                        break
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.warning(f"Unexpected error downloading from {full}: {str(e)}")
                    if attempt == max_retries:
                        break
                    await asyncio.sleep(1)
                    
        # If we reach here, all URLs failed
        logger.error(f"Failed to download file from any URL: {urls}")
        raise RuntimeError(f"Не вдалося завантажити файл із жодного URL: {urls}")


def normalize_jira_domain(raw: str) -> str:
    """
    Прибирає http:// або https:// з початку рядка.
    """
    return raw.replace('https://', '').replace('http://', '')

def build_attachment_urls(jira_domain: str, attachment_id: str, filename: str, content_url: Optional[str] = None) -> list[str]:
    """
    Повертає перелік можливих URL для скачування вкладення.
    
    Args:
        jira_domain: домен Jira
        attachment_id: ID вкладення
        filename: ім'я файлу
        content_url: URL контенту, якщо є в даних attachment
        
    Returns:
        list[str]: Список можливих URL для завантаження
    """
    if not attachment_id:
        logger.warning("Пустий ID вкладення, спробуємо альтернативні способи завантаження")
        # Якщо немає ID, спробуємо використати content_url або побудувати альтернативні URL
        if not content_url and not filename:
            logger.error("Немає ні ID, ні content_url, ні filename для завантаження")
            return []
        
    if not jira_domain:
        logger.error("Не вказано домен Jira")
        return []
        
    if not filename:
        logger.warning("Не вказано ім'я файлу, використовуємо 'attachment' як дефолтне")
        filename = "attachment"
    
    domain = normalize_jira_domain(jira_domain)
    quoted = quote(filename)
    urls = []
    
    # Якщо немає attachment_id, спробуємо використати content_url
    if not attachment_id:
        if content_url:
            # Нормалізуємо content_url
            if not content_url.startswith(('http://', 'https://')):
                if content_url.startswith('/'):
                    content_url = f"https://{domain}{content_url}"
                else:
                    content_url = f"https://{domain}/{content_url}"
            urls.append(content_url)
            logger.info(f"Додано content_url для файлу без ID: {content_url}")
        
        # Спробуємо побудувати URL за іменем файлу для inline зображень
        # Деякі inline зображення можуть бути доступні через загальні URL
        alternative_urls = [
            f"https://{domain}/secure/attachment/{quoted}",
            f"https://{domain}/download/attachments/temp/{quoted}",
            f"https://{domain}/images/{quoted}",
            f"https://{domain}/secure/thumbnail/{quoted}",
        ]
        urls.extend(alternative_urls)
        logger.info(f"Додано {len(alternative_urls)} альтернативних URL для файлу без ID")
        return urls
    
    # Нові URL шаблони для Jira Cloud з валідним ID
    urls = [
        f"https://{domain}/secure/attachment/{attachment_id}/{quoted}",
        f"https://{domain}/rest/api/3/attachment/{attachment_id}/content",
        f"https://{domain}/rest/api/2/attachment/{attachment_id}/content",
        f"https://{domain}/attachments/{attachment_id}/download/{quoted}",
        f"https://{domain}/download/attachments/{attachment_id}/{quoted}"
    ]
    
    # Додаємо content_url, якщо він є і виглядає валідним
    if content_url:
        # Нормалізуємо URL
        if not content_url.startswith(('http://', 'https://')):
            if content_url.startswith('/'):
                content_url = f"https://{domain}{content_url}"
            else:
                content_url = f"https://{domain}/{content_url}"
                
        # Перевіряємо чи URL містить attachment ID
        if attachment_id in content_url:
            # Додаємо на початок як пріоритетний URL
            urls.insert(0, content_url)
        else:
            # Додаємо в кінець як резервний URL
            urls.append(content_url)
            
    logger.debug(f"Generated URLs for attachment {attachment_id}: {urls}")
    return urls

async def get_issue_attachments_by_filename(issue_key: str, filename: str) -> Optional[dict]:
    """
    Отримує всі вкладення задачі через API і знаходить відповідне зображення за іменем файлу.
    Це корисно для inline зображень, які не мають правильного attachment ID у webhook.
    
    Args:
        issue_key: ключ задачі Jira (наприклад, SD-42192)
        filename: ім'я файлу для пошуку
        
    Returns:
        dict: дані вкладення або None, якщо не знайдено
    """
    from config.config import JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN
    
    try:
        # Use basic auth credentials
        auth = httpx.BasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
        
        async with httpx.AsyncClient(timeout=30, auth=auth, follow_redirects=True) as client:
            # Отримуємо дані задачі з вкладеннями
            url = f"https://{normalize_jira_domain(JIRA_DOMAIN)}/rest/api/3/issue/{issue_key}?fields=attachment"
            
            logger.info(f"Запитуємо вкладення задачі {issue_key} через API")
            resp = await client.get(url)
            resp.raise_for_status()
            
            issue_data = resp.json()
            attachments = issue_data.get('fields', {}).get('attachment', [])
            
            logger.info(f"Знайдено {len(attachments)} вкладень у задачі {issue_key}")
            
            # Шукаємо вкладення за іменем файлу
            for attachment in attachments:
                att_filename = attachment.get('filename', '')
                if att_filename == filename:
                    logger.info(f"Знайдено відповідне вкладення: {att_filename} (ID: {attachment.get('id')})")
                    return attachment
            
            # Якщо точна відповідність не знайдена, шукаємо частичну
            for attachment in attachments:
                att_filename = attachment.get('filename', '')
                if filename in att_filename or att_filename in filename:
                    logger.info(f"Знайдено схоже вкладення: {att_filename} (ID: {attachment.get('id')})")
                    return attachment
                    
            logger.warning(f"Не знайдено вкладення з іменем '{filename}' у задачі {issue_key}")
            return None
            
    except Exception as e:
        logger.error(f"Помилка отримання вкладень задачі {issue_key}: {str(e)}")
        return None
