"""
Інтегратор: приклад використання утиліт із jira_attachment_utils для обробки webhook-подій.
"""

import asyncio
import logging
import re
from .jira_attachment_utils import build_attachment_urls, download_file_from_jira

# Ініціалізуємо логування
logger = logging.getLogger(__name__)


async def process_attachments_for_issue(
    jira_domain: str, attachments: list[dict], issue_key: str, send_file_cb
) -> tuple[int, int]:
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
        att_id = str(att.get("id", ""))
        if not att_id and "self" in att:
            # Try to extract ID from self URL
            match = re.search(r"/attachment/(\d+)", att.get("self", ""))
            if match:
                att_id = match.group(1)
                logger.info(f"Extracted attachment ID from self URL: {att_id}")

        name = att.get("filename", "") or att.get("name", f"file_{att_id}")
        mime_type = att.get("mimeType", "") or att.get("contentType", "")
        content_url = att.get("content", "") or att.get("self", "")

        logger.info(f"Processing attachment {idx}/{total}: {name} (ID: {att_id})")

        # Спеціальна обробка для вкладень без ID (inline зображення)
        if not att_id:
            logger.info(f"Вкладення без ID, шукаємо через API задачі: {name}")
            api_attachment = await get_issue_attachments_by_filename(issue_key, name)
            if api_attachment:
                # Використовуємо дані з API
                att_id = str(api_attachment.get("id", ""))
                content_url = api_attachment.get("content", "")
                if not mime_type:
                    mime_type = api_attachment.get("mimeType", "")
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
            logger.info(
                f"Sending attachment {name} ({len(file_bytes)} bytes) to Telegram"
            )
            await send_file_cb(
                {
                    "chat_id": att.get("chat_id", ""),
                    "file_name": name,
                    "file_bytes": file_bytes,
                    "mime_type": mime_type,
                    "issue_key": issue_key,
                }
            )

            success += 1
            logger.info(f"Successfully processed attachment {name}")

            # Невелика пауза між відправкою файлів
            if idx < total:
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Error processing attachment {name}: {str(e)}", exc_info=True)
            errors += 1
            continue

    logger.info(
        f"Attachment processing complete for {issue_key}: {success} successful, {errors} failed"
    )
    return success, errors


def _infer_mime_type(filename: str) -> str:
    """Helper function to infer MIME type from filename extension"""
    ext = filename.lower().split(".")[-1] if "." in filename else ""

    # Images
    if ext in ["jpg", "jpeg"]:
        return "image/jpeg"
    elif ext == "png":
        return "image/png"
    elif ext == "gif":
        return "image/gif"
    elif ext == "bmp":
        return "image/bmp"
    elif ext == "webp":
        return "image/webp"
    elif ext == "svg":
        return "image/svg+xml"
    elif ext == "ico":
        return "image/x-icon"

    # Videos
    elif ext == "mp4":
        return "video/mp4"
    elif ext == "avi":
        return "video/x-msvideo"
    elif ext == "mov":
        return "video/quicktime"
    elif ext == "wmv":
        return "video/x-ms-wmv"
    elif ext == "flv":
        return "video/x-flv"
    elif ext == "mkv":
        return "video/x-matroska"

    # Audio
    elif ext == "mp3":
        return "audio/mpeg"
    elif ext == "wav":
        return "audio/wav"
    elif ext == "flac":
        return "audio/flac"
    elif ext == "aac":
        return "audio/aac"
    elif ext == "ogg":
        return "audio/ogg"

    # Documents
    elif ext == "pdf":
        return "application/pdf"
    elif ext == "doc":
        return "application/msword"
    elif ext == "docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif ext == "xls":
        return "application/vnd.ms-excel"
    elif ext == "xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif ext == "ppt":
        return "application/vnd.ms-powerpoint"
    elif ext == "pptx":
        return (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )
    elif ext == "odt":
        return "application/vnd.oasis.opendocument.text"
    elif ext == "ods":
        return "application/vnd.oasis.opendocument.spreadsheet"
    elif ext == "odp":
        return "application/vnd.oasis.opendocument.presentation"
    elif ext == "rtf":
        return "application/rtf"

    # Archives
    elif ext == "zip":
        return "application/zip"
    elif ext == "rar":
        return "application/x-rar-compressed"
    elif ext == "7z":
        return "application/x-7z-compressed"
    elif ext == "tar":
        return "application/x-tar"
    elif ext == "gz":
        return "application/gzip"
    elif ext == "bz2":
        return "application/x-bzip2"

    # Text files
    elif ext == "txt":
        return "text/plain"
    elif ext == "csv":
        return "text/csv"
    elif ext == "json":
        return "application/json"
    elif ext == "xml":
        return "application/xml"
    elif ext == "html":
        return "text/html"
    elif ext == "css":
        return "text/css"
    elif ext == "js":
        return "application/javascript"

    # Programming files
    elif ext == "py":
        return "text/x-python"
    elif ext == "java":
        return "text/x-java-source"
    elif ext == "cpp":
        return "text/x-c++src"
    elif ext == "c":
        return "text/x-csrc"
    elif ext == "php":
        return "text/x-php"
    elif ext == "sql":
        return "text/x-sql"

    # Default for unknown types
    else:
        return "application/octet-stream"
