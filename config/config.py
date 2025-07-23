#config.py

import os
from pathlib import Path
from dotenv import load_dotenv

# Завантажуємо .env з кореню проєкту
env_path = Path(__file__).parent / "credentials.env"
load_dotenv(dotenv_path=env_path)

# Telegram
TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN") or ""
# Telegram bot token
TELEGRAM_BOT_TOKEN = TELEGRAM_TOKEN

# Jira
JIRA_BASE_URL: str = os.getenv("JIRA_DOMAIN") or ""  # наприклад https://euromix.atlassian.net
JIRA_EMAIL: str = os.getenv("JIRA_EMAIL") or ""
JIRA_API_TOKEN: str = os.getenv("JIRA_API_TOKEN", "").strip().strip('"')
JIRA_PROJECT_KEY: str = os.getenv("JIRA_PROJECT_KEY") or ""
JIRA_ISSUE_TYPE: str = os.getenv("JIRA_ISSUE_TYPE") or ""
JIRA_REPORTER_ACCOUNT_ID: str = os.getenv("JIRA_REPORTER_ACCOUNT_ID") or ""
JIRA_DOMAIN: str = os.getenv("JIRA_DOMAIN") or ""

# Webhook (якщо використовуємо)
WEBHOOK_URL: str | None = os.getenv("WEBHOOK_URL", None)
WEBHOOK_HOST: str = os.getenv("WEBHOOK_HOST", "0.0.0.0")
WEBHOOK_SECRET_KEY: str | None = os.getenv("WEBHOOK_SECRET_KEY", None)
WEBHOOK_PORT: int = int(os.getenv("WEBHOOK_PORT", 8443))
SSL_CERT_PATH: str | None = os.getenv("SSL_CERT_PATH", None)
SSL_KEY_PATH: str | None = os.getenv("SSL_KEY_PATH", None)

# Google Sheets
_google_creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH") or ""
if _google_creds_path and not os.path.isabs(_google_creds_path):
    # Если путь относительный, делаем его относительно корня проекта
    project_root = Path(__file__).parent.parent  
    GOOGLE_CREDENTIALS_PATH = str(project_root / _google_creds_path)
else:
    GOOGLE_CREDENTIALS_PATH = _google_creds_path

GOOGLE_SHEET_USERS_ID: str = os.getenv("GOOGLE_SHEET_USERS_ID", os.getenv("GOOGLE_SHEET_users_ID")) or ""

# Mapping file
FIELDS_MAPPING_FILE: str = os.getenv("FIELDS_MAPPING_FILE", "fields_mapping.yaml")
