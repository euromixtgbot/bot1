#!/usr/bin/env python3
"""
Аналіз реальних webhook даних для виявлення проблем з issue_key
"""

import re

# Реальні дані з логів
real_attachment_created_log = """
14:08:27,258 - 🔔 ATTACHMENT_CREATED EVENT RECEIVED
14:08:27,258 - 📎 Processing attachment_created: New Text Document (7bdd763d-760d-4197-8b15-1364ca6a95aa).txt (ID: 135644)
14:08:34,936 - ❌ Cannot determine issue key for attachment 135644. Skipping cache.
"""

real_comment_created_log = """
14:08:27,733 - Processing new comment for issue SD-42699
14:08:28,196 - 📦 Found 0 cached attachments (should be 2!)
"""


def analyze_webhook_structure():
    """Аналіз структури webhook подій"""
    print("🔍 АНАЛІЗ WEBHOOK СТРУКТУРИ")
    print("=" * 60)

    # Типова структура attachment_created webhook без issue
    typical_attachment_webhook = {
        "webhookEvent": "attachment_created",
        "timestamp": 1720704507258,
        "user": {"accountId": "5f27b6facdb7b4001be9f12f", "displayName": "User Name"},
        "attachment": {
            "id": "135644",
            "filename": "New Text Document (7bdd763d-760d-4197-8b15-1364ca6a95aa).txt",
            "mimeType": "text/plain",
            "size": 123,
            "self": "https://euromix.atlassian.net/rest/api/3/attachment/135644",
            "content": "https://euromix.atlassian.net/rest/api/3/attachment/135644/content",
        },
        # ПРОБЛЕМА: Відсутнє поле "issue"!
    }

    # Типова структура comment_created з issue
    typical_comment_webhook = {
        "webhookEvent": "comment_created",
        "timestamp": 1720704507733,
        "issue": {
            "key": "SD-42699",  # ← Тут є issue_key!
            "fields": {"attachment": []},  # Але вкладення порожні
        },
        "comment": {
            "author": {"displayName": "User"},
            "body": "Comment with embedded: !0142.JPG|data-attachment-id=135645!",
        },
    }

    print("❌ ПРОБЛЕМА: attachment_created події НЕ МІСТЯТЬ issue поле")
    print("✅ РІШЕННЯ: comment_created події МІСТЯТЬ issue поле")
    print()
    print("📋 СТРАТЕГІЇ ОТРИМАННЯ ISSUE_KEY:")
    print("1. 🌐 API запит: /rest/api/3/attachment/{id}")
    print("2. 🔗 URL parsing: витягти з attachment.self або content URL")
    print("3. 📝 Fallback: використати тимчасове зберігання без issue_key")

    return typical_attachment_webhook, typical_comment_webhook


def test_url_parsing():
    """Тест витягування issue_key з URL"""
    print("\n🔧 ТЕСТ ВИТЯГУВАННЯ ISSUE_KEY З URL")
    print("-" * 50)

    test_urls = [
        "https://euromix.atlassian.net/rest/api/3/attachment/135644",
        "https://euromix.atlassian.net/rest/api/3/attachment/135644/content",
        "https://euromix.atlassian.net/secure/attachment/135644/filename.txt",
        "https://euromix.atlassian.net/browse/SD-42699/attachment/135644",
    ]

    for url in test_urls:
        print(f"🔗 URL: {url}")

        # Спроба витягти attachment ID
        attachment_id_match = re.search(r"/attachment/(\d+)", url)
        if attachment_id_match:
            att_id = attachment_id_match.group(1)
            print(f"   ✅ Attachment ID: {att_id}")

        # Спроба витягти issue key (якщо є)
        issue_key_match = re.search(r"/browse/([A-Z]+-\d+)", url)
        if issue_key_match:
            issue_key = issue_key_match.group(1)
            print(f"   ✅ Issue Key: {issue_key}")
        else:
            print("   ❌ Issue Key: не знайдено")
        print()


def propose_solution():
    """Пропозиція рішення"""
    print("💡 РЕКОМЕНДОВАНЕ РІШЕННЯ")
    print("=" * 60)

    solution_steps = [
        "1. 🕒 ТИМЧАСОВЕ КЕШУВАННЯ БЕЗ ISSUE_KEY",
        "   - Зберігати всі attachment_created події в глобальному кеші",
        "   - Використовувати attachment_id як ключ",
        "   - При comment_created шукати відповідні attachments",
        "",
        "2. 🔄 ПОКРАЩЕНИЙ MATCHING АЛГОРИТМ",
        "   - Порівнювати часові мітки (±30 секунд)",
        "   - Зіставляти імена файлів",
        "   - Використовувати embedded attachments як підказки",
        "",
        "3. 🌐 АСИНХРОННІ API ЗАПИТИ",
        "   - Робити API запити в фоновому режимі",
        "   - Не блокувати webhook обробку",
        "   - Використовувати результати для наступних подій",
        "",
        "4. 📝 FALLBACK СТРАТЕГІЇ",
        "   - Якщо API недоступний - використовувати часові зіставлення",
        "   - Якщо невдалося зіставити - логувати та пропускати",
        "   - Зберігати статистику успішності для моніторингу",
    ]

    for step in solution_steps:
        print(step)


if __name__ == "__main__":
    analyze_webhook_structure()
    test_url_parsing()
    propose_solution()

    print("\n🎯 НАСТУПНІ КРОКИ:")
    print("1. Реалізувати тимчасове кешування за attachment_id")
    print("2. Додати алгоритм зіставлення за часом та іменем файлу")
    print("3. Покращити API запити з кращою обробкою помилок")
    print("4. Протестувати з реальними webhook подіями")
