# google_sheets_service.py

import re
from typing import Optional, Tuple, Dict, List, Union
from functools import wraps

from gspread.auth import service_account
from gspread.client import Client
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError, SpreadsheetNotFound

from config.config import GOOGLE_CREDENTIALS_PATH, GOOGLE_SHEET_USERS_ID


class GoogleSheetsError(Exception):
    """Base exception for Google Sheets related errors"""


def handle_google_api_errors(func):
    """Decorator для обробки помилок Google Sheets API"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except APIError as e:
            raise GoogleSheetsError(f"Google Sheets API error: {str(e)}") from e
        except SpreadsheetNotFound:
            raise GoogleSheetsError(f"Spreadsheet not found: {GOOGLE_SHEET_USERS_ID}")
        except Exception as e:
            raise GoogleSheetsError(f"Unexpected error: {str(e)}") from e

    return wrapper


# Підключаємося до Google Sheets через Service Account
_SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

try:
    # Modern gspread API - use service_account method or Client directly
    try:
        # Method 1: Try using service_account if credentials file is JSON
        _gc = service_account(filename=GOOGLE_CREDENTIALS_PATH)
    except Exception:
        # Method 2: Fallback to manual credentials loading for newer gspread versions
        _creds = Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_PATH, scopes=_SCOPE
        )
        # Use Client constructor instead of authorize
        _gc = Client(auth=_creds)

    _sheet = _gc.open_by_key(GOOGLE_SHEET_USERS_ID).sheet1

    # Зчитуємо заголовки колонок один раз
    _HEADERS = _sheet.row_values(1)
    _COLUMN_INDEX = {name: idx + 1 for idx, name in enumerate(_HEADERS)}

except FileNotFoundError:
    raise GoogleSheetsError(f"Credentials file not found: {GOOGLE_CREDENTIALS_PATH}")
except (APIError, SpreadsheetNotFound) as e:
    raise GoogleSheetsError(f"Failed to initialize Google Sheets: {str(e)}")


def _normalize_phone(phone: str) -> str:
    """
    Видаляє непотрібні символи, залишає тільки цифри.

    Args:
        phone (str): Номер телефону в будь-якому форматі

    Returns:
        str: Тільки цифри номера телефону
    """
    return re.sub(r"\D", "", phone)


@handle_google_api_errors
def find_user_by_phone(
    phone: str,
) -> Optional[Tuple[Dict[str, Union[int, float, str]], int]]:
    """
    Шукає користувача за номером телефону.

    Args:
        phone (str): Номер телефону для пошуку

    Returns:
        Optional[Tuple[Dict[str, Union[int, float, str]], int]]: Кортеж (record, row_index) або None

    Raises:
        GoogleSheetsError: При помилках з API
        ValueError: Якщо телефон пустий
    """
    if not phone:
        raise ValueError("Phone number cannot be empty")

    norm = _normalize_phone(phone)
    if not norm:
        raise ValueError("Phone number must contain at least one digit")

    try:
        all_records = _sheet.get_all_records()
        for idx, record in enumerate(all_records, start=2):
            if _normalize_phone(str(record.get("mobile_number", ""))) == norm:
                return record, idx
        return None
    except Exception as e:
        raise GoogleSheetsError(f"Error searching for user: {str(e)}")


@handle_google_api_errors
def find_user_by_telegram_id(
    telegram_id: str,
) -> Optional[Tuple[Dict[str, Union[int, float, str]], int]]:
    """
    Шукає користувача за Telegram ID.

    Args:
        telegram_id (str): Telegram ID для пошуку

    Returns:
        Optional[Tuple[Dict[str, Union[int, float, str]], int]]: Кортеж (record, row_index) або None

    Raises:
        GoogleSheetsError: При помилках з API
        ValueError: Якщо Telegram ID пустий
    """
    if not telegram_id:
        raise ValueError("Telegram ID cannot be empty")

    # Нормалізуємо ID: видаляємо пробіли і апострофи
    normalized_id = str(telegram_id).strip().replace("'", "")
    if not normalized_id:
        raise ValueError("Telegram ID must contain at least one character")

    try:
        all_records = _sheet.get_all_records()
        for idx, record in enumerate(all_records, start=2):
            # Normalize stored telegram_id by removing apostrophes
            stored_id = str(record.get("telegram_id", "")).strip().replace("'", "")
            if stored_id and stored_id == normalized_id:
                return record, idx
        return None
    except Exception as e:
        raise GoogleSheetsError(f"Error searching for user: {str(e)}")


@handle_google_api_errors
def update_user_telegram(row: int, telegram_id: str, telegram_username: str) -> None:
    """
    Записує telegram_id та telegram_username у відповідні колонки.

    Args:
        row (int): Номер рядка для оновлення
        telegram_id (str): ID користувача в Telegram
        telegram_username (str): Username користувача в Telegram

    Raises:
        GoogleSheetsError: При помилках з API
        ValueError: При некоректних вхідних даних
    """
    if row < 2:
        raise ValueError("Row number must be greater than 1")
    if not telegram_id:
        raise ValueError("Telegram ID cannot be empty")

    # Normalize telegram_id by removing apostrophes
    normalized_telegram_id = str(telegram_id).strip().replace("'", "")

    batch_updates = []
    if "telegram_id" in _COLUMN_INDEX:
        col_letter = chr(
            64 + _COLUMN_INDEX["telegram_id"]
        )  # Convert column index to letter
        batch_updates.append(
            {"range": f"{col_letter}{row}", "values": [[normalized_telegram_id]]}
        )
    if "telegram_username" in _COLUMN_INDEX and telegram_username:
        col_letter = chr(
            64 + _COLUMN_INDEX["telegram_username"]
        )  # Convert column index to letter
        batch_updates.append(
            {"range": f"{col_letter}{row}", "values": [[telegram_username]]}
        )

    if batch_updates:
        _sheet.batch_update(batch_updates)


@handle_google_api_errors
def add_new_user(record: Dict[str, str]) -> int:
    """
    Додає нового користувача в кінець таблиці.

    Args:
        record (Dict[str, str]): Дані користувача

    Returns:
        int: Номер рядка, куди додано запис

    Raises:
        GoogleSheetsError: При помилках з API
        ValueError: Якщо запис пустий
    """
    if not record:
        raise ValueError("Record cannot be empty")

    # Перевіряємо наявність хоча б якихось даних користувача
    required_any_one = {"full_name", "telegram_id", "mobile_number"}
    if not any(field in record and record[field] for field in required_any_one):
        raise ValueError(
            "At least one of required fields must be present: full_name, telegram_id or mobile_number"
        )

    # Normalize telegram_id if present
    if "telegram_id" in record and record["telegram_id"]:
        record["telegram_id"] = str(record["telegram_id"]).strip().replace("'", "")

    # Normalize mobile_number if present - видаляємо знак "+"
    if "mobile_number" in record and record["mobile_number"]:
        record["mobile_number"] = _normalize_phone(str(record["mobile_number"]))

    # Формуємо рядок у порядку _HEADERS
    row = [record.get(col, "") for col in _HEADERS]
    _sheet.append_row(row)
    return len(_sheet.get_all_values())


@handle_google_api_errors
def get_all_headers() -> List[str]:
    """
    Повертає список всіх заголовків таблиці.

    Returns:
        List[str]: Список заголовків

    Raises:
        GoogleSheetsError: При помилках з API
    """
    return _HEADERS.copy()
