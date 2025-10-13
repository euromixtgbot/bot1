# filepath: /Users/home/Documents/simple_bot/fixed_issue_formatter.py
"""Модуль для форматирования информации о задаче в Jira"""
import logging
from typing import Dict, Any

# Логирование
logger = logging.getLogger(__name__)


def format_issue_info(issue: Dict[str, Any]) -> Dict[str, str]:
    """
    Форматирует информацию о задаче для отображения пользователю

    Args:
        issue: Словарь с данными задачи из Jira

    Returns:
        Dict[str, str]: Словарь с отформатированными полями
    """
    logger.info(f"Форматирование задачи: {issue.get('key', '[нет ключа]')}")

    # Обработка статуса с учетом различных вариантов данных
    status = issue.get("status", "Невідомо")
    if isinstance(status, dict):
        status = status.get("name", status.get("value", "Невідомо"))
    if " (" in status:
        status = status.split(" (")[0].strip()  # Убираем текст в скобках из статуса

    # Обработка подразделения с учетом различных вариантов данных
    division = issue.get("division", "Невідомо")
    if isinstance(division, dict):
        division = division.get("value", division.get("name", "Невідомо"))
    elif isinstance(division, list) and division:
        if isinstance(division[0], dict):
            division = division[0].get("value", division[0].get("name", "Невідомо"))
        else:
            division = str(division[0])

    # Обработка сервиса с учетом различных вариантов данных
    service = issue.get("service", "Невідомо")
    if isinstance(service, dict):
        service = service.get("value", service.get("name", "Невідомо"))
    elif isinstance(service, list) and service:
        if isinstance(service[0], dict):
            service = service[0].get("value", service[0].get("name", "Невідомо"))
        else:
            service = str(service[0])

    # Обработка имени автора
    reporter_name = issue.get("reporter_name", "Невідомо")
    if isinstance(reporter_name, dict):
        reporter_name = reporter_name.get(
            "displayName", reporter_name.get("name", "Невідомо")
        )

    # Обработка департамента
    department = issue.get("department", "Невідомо")
    if isinstance(department, dict):
        department = department.get("value", department.get("name", "Невідомо"))
    elif isinstance(department, list) and department:
        if isinstance(department[0], dict):
            department = department[0].get(
                "value", department[0].get("name", "Невідомо")
            )
        else:
            department = str(department[0])

    # Обработка описания и краткого содержания
    description = issue.get("description", "")
    summary = issue.get("summary", "")

    # Улучшенный парсер для Jira ADF формата описания
    if isinstance(description, dict):
        try:
            if "content" in description:
                # Более гибкий парсер для извлечения текста из Jira ADF формата
                text_parts = []
                for content in description.get("content", []):
                    # Обработка разных типов контента
                    content_type = content.get("type", "")

                    if content_type == "paragraph":
                        paragraph_parts = []
                        for part in content.get("content", []):
                            if "text" in part:
                                paragraph_parts.append(part["text"])
                        if paragraph_parts:
                            text_parts.append(" ".join(paragraph_parts))

                    elif content_type == "bulletList" or content_type == "orderedList":
                        for list_item in content.get("content", []):
                            item_parts = []
                            for paragraph in list_item.get("content", []):
                                for text_part in paragraph.get("content", []):
                                    if "text" in text_part:
                                        item_parts.append(text_part["text"])
                            if item_parts:
                                text_parts.append("• " + " ".join(item_parts))

                description = "\n".join(text_parts)
            else:
                description = str(description)
        except Exception as e:
            logger.error(f"Ошибка парсинга ADF описания: {e}")
            description = "Ошибка парсинга описания"

    # Обрабатываем комментарии, если они есть
    comments = issue.get("comments", [])
    if isinstance(comments, list):
        comments_list = []
        for comment in comments:
            if isinstance(comment, dict):
                # Извлекаем автора комментария
                author = comment.get("author", {}).get("displayName", "Невідомо")

                # Извлекаем текст комментария
                comment_body = comment.get("body", "")
                if isinstance(comment_body, dict) and "content" in comment_body:
                    # Парсим ADF формат комментария
                    body_parts = []
                    for content in comment_body.get("content", []):
                        if content.get("type") == "paragraph":
                            for part in content.get("content", []):
                                if "text" in part:
                                    body_parts.append(part["text"])
                    comment_text = " ".join(body_parts)
                else:
                    comment_text = str(comment_body)

                # Извлекаем дату комментария
                created = (
                    comment.get("created", "").split("T")[0]
                    if "T" in comment.get("created", "")
                    else comment.get("created", "")
                )

                comments_list.append(f"{author} [{created}]: {comment_text}")
    else:
        comments_list = []

    # Собираем финальный словарь с данными
    formatted = {
        "key": issue.get("key", "Невідомо"),
        "summary": summary,
        "status": status,
        "reporter": reporter_name,
        "division": division,
        "department": department,
        "service": service,
        "description": description,
        "comments": "\n".join(comments_list) if comments_list else "Немає коментарів",
    }

    return formatted


def format_issue_text(formatted: Dict[str, str]) -> str:
    """
    Преобразует отформатированные данные о задаче в единый текст для вывода

    Args:
        formatted: Словарь с отформатированными данными о задаче

    Returns:
        str: Текстовое представление информации о задаче
    """
    text_parts = [
        f"📋 Задача: {formatted.get('key', 'Невідомо')}",
        f"✏️ Тема: {formatted.get('summary', 'Відсутня')}",
        f"📊 Статус: {formatted.get('status', 'Невідомо')}",
        f"👤 Автор: {formatted.get('reporter', 'Невідомо')}",
        f"🏢 Підрозділ: {formatted.get('division', 'Невідомо')}",
        f"🏬 Департамент: {formatted.get('department', 'Невідомо')}",
        f"🛠️ Сервіс: {formatted.get('service', 'Невідомо')}",
        # f"\n📝 Опис: {formatted.get('description', 'Відсутній')}"
    ]

    return "\n".join(text_parts)
