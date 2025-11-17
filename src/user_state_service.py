#!/usr/bin/env python3
"""
Сервіс для збереження та відновлення стану користувачів
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, cast

logger = logging.getLogger(__name__)


class UserStateManager:
    """Менеджер для збереження стану користувачів у файли"""

    def __init__(self, base_dir: str = "/home/Bot1/user_states"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True)

    def _get_user_file(self, telegram_id: int) -> Path:
        """Повертає шлях до файлу користувача"""
        return self.base_dir / f"user_{telegram_id}.json"

    def save_user_state(self, telegram_id: int, state_data: Dict[str, Any]) -> bool:
        """Зберігає стан користувача у файл"""
        try:
            user_file = self._get_user_file(telegram_id)

            # Додаємо метадані
            data = {
                "telegram_id": telegram_id,
                "last_updated": datetime.now().isoformat(),
                "state": state_data,
            }

            with open(user_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.info(f"Збережено стан користувача {telegram_id} у файл {user_file}")
            return True

        except Exception as e:
            logger.error(f"Помилка збереження стану користувача {telegram_id}: {e}")
            return False

    def load_user_state(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Завантажує стан користувача з файлу"""
        try:
            user_file = self._get_user_file(telegram_id)

            if not user_file.exists():
                logger.info(f"Файл стану для користувача {telegram_id} не знайдено")
                return None

            with open(user_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            logger.info(
                f"Завантажено стан користувача {telegram_id} з файлу {user_file}"
            )
            return cast(Dict[str, Any], data.get("state", {}))

        except Exception as e:
            logger.error(f"Помилка завантаження стану користувача {telegram_id}: {e}")
            return None

    def delete_user_state(self, telegram_id: int) -> bool:
        """Видаляє файл стану користувача"""
        try:
            user_file = self._get_user_file(telegram_id)

            if user_file.exists():
                user_file.unlink()
                logger.info(f"Видалено файл стану користувача {telegram_id}")
                return True
            else:
                logger.info(f"Файл стану користувача {telegram_id} не існує")
                return False

        except Exception as e:
            logger.error(f"Помилка видалення стану користувача {telegram_id}: {e}")
            return False

    def list_all_users(self) -> list:
        """Повертає список всіх користувачів з файлами стану"""
        try:
            user_files = list(self.base_dir.glob("user_*.json"))
            telegram_ids = []

            for file_path in user_files:
                try:
                    # Витягуємо telegram_id з назви файлу
                    filename = file_path.stem  # user_123456789
                    telegram_id = int(filename.split("_")[1])
                    telegram_ids.append(telegram_id)
                except (ValueError, IndexError):
                    logger.warning(f"Неправильна назва файлу: {file_path}")
                    continue

            return telegram_ids

        except Exception as e:
            logger.error(f"Помилка отримання списку користувачів: {e}")
            return []

    def get_user_info(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Повертає повну інформацію про користувача (включно з метаданими)"""
        try:
            user_file = self._get_user_file(telegram_id)

            if not user_file.exists():
                return None

            with open(user_file, "r", encoding="utf-8") as f:
                return cast(Dict[str, Any], json.load(f))

        except Exception as e:
            logger.error(
                f"Помилка отримання інформації про користувача {telegram_id}: {e}"
            )
            return None


def save_user_profile(
    telegram_id: int, user_data: Dict[str, Any], status: str = "active"
) -> bool:
    """Зберігає повний профіль користувача як резервну копію та кеш"""
    try:
        # Завантажуємо існуючий стан, щоб зберегти bot_state
        current_state = user_state_manager.load_user_state(telegram_id)

        profile_data = {
            "profile": user_data,
            "status": status,  # active, registration_in_progress, inactive
            "sync_with_google": True,
            "type": "user_profile",
        }

        # Зберігаємо існуючий bot_state, якщо він є
        if current_state and "bot_state" in current_state:
            profile_data["bot_state"] = current_state["bot_state"]
            logger.info(
                f"Збережено існуючий bot_state для користувача {telegram_id}: {current_state['bot_state']}"
            )

        return user_state_manager.save_user_state(telegram_id, profile_data)
    except Exception as e:
        logger.error(f"Помилка збереження профілю користувача {telegram_id}: {e}")
        return False


def load_user_profile(telegram_id: int) -> Optional[Dict[str, Any]]:
    """Завантажує повний профіль користувача з локального кешу"""
    try:
        state = user_state_manager.load_user_state(telegram_id)
        if state and state.get("type") == "user_profile":
            return cast(Dict[str, Any], state.get("profile", {}))
        return None
    except Exception as e:
        logger.error(f"Помилка завантаження профілю користувача {telegram_id}: {e}")
        return None


def update_user_sync_status(telegram_id: int, synced: bool) -> bool:
    """Оновлює статус синхронізації з Google Sheets"""
    try:
        state = user_state_manager.load_user_state(telegram_id)
        if state and state.get("type") == "user_profile":
            state["sync_with_google"] = synced
            state["last_sync"] = datetime.now().isoformat()
            return user_state_manager.save_user_state(telegram_id, state)
        return False
    except Exception as e:
        logger.error(f"Помилка оновлення статусу синхронізації {telegram_id}: {e}")
        return False


def list_all_cached_users() -> List[Dict[str, Any]]:
    """Повертає список всіх користувачів з локального кешу"""
    try:
        all_users = []
        telegram_ids = user_state_manager.list_all_users()

        for telegram_id in telegram_ids:
            profile = load_user_profile(telegram_id)
            if profile:
                profile["telegram_id"] = telegram_id
                all_users.append(profile)

        return all_users
    except Exception as e:
        logger.error(f"Помилка отримання списку користувачів: {e}")
        return []


# Глобальний екземпляр менеджера
user_state_manager = UserStateManager()


def save_registration_state(
    telegram_id: int, registration_data: Dict[str, Any], registration_step: str
) -> bool:
    """Зберігає стан реєстрації користувача"""
    state_data = {
        "registration": registration_data,
        "registration_step": registration_step,
        "type": "registration_in_progress",
    }
    return user_state_manager.save_user_state(telegram_id, state_data)


def load_registration_state(telegram_id: int) -> Optional[Dict[str, Any]]:
    """Завантажує стан реєстрації користувача (тільки активні реєстрації)"""
    state = user_state_manager.load_user_state(telegram_id)
    if state and state.get("type") == "registration_in_progress":
        # Перевіряємо чи не застаріла реєстрація (старше 24 годин)
        from datetime import datetime, timedelta

        try:
            user_info = user_state_manager.get_user_info(telegram_id)
            if user_info and "last_updated" in user_info:
                last_updated = datetime.fromisoformat(user_info["last_updated"])
                if datetime.now() - last_updated > timedelta(hours=24):
                    logger.info(
                        f"Очищення застарілої реєстрації для користувача {telegram_id}"
                    )
                    user_state_manager.delete_user_state(telegram_id)
                    return None
        except Exception as e:
            logger.warning(
                f"Помилка перевірки давності реєстрації для {telegram_id}: {e}"
            )

        return state
    return None


def complete_registration(telegram_id: int) -> bool:
    """Зберігає файл як завершену реєстрацію для історії"""
    try:
        # Завантажуємо поточний стан
        current_state = user_state_manager.load_user_state(telegram_id)
        if not current_state:
            logger.warning(f"Немає поточного стану для користувача {telegram_id}")
            return False

        # Змінюємо тип на завершений та додаємо час завершення
        completed_state = {
            **current_state,
            "type": "registration_completed",
            "completed_at": datetime.now().isoformat(),
        }

        # Зберігаємо оновлений стан
        result = user_state_manager.save_user_state(telegram_id, completed_state)
        logger.info(f"Реєстрацію користувача {telegram_id} позначено як завершену")
        return result

    except Exception as e:
        logger.error(f"Помилка завершення реєстрації користувача {telegram_id}: {e}")
        return False


# === НОВА СИСТЕМА СТАНІВ БОТА ===


class BotState:
    """Константи для станів бота"""

    REGISTRATION = "registration"  # 1. Реєстрація або авторизація
    AUTHORIZED_NO_TASKS = (
        "authorized_no_tasks"  # 2. Авторизований, немає відкритих задач
    )
    AUTHORIZED_WITH_TASK = "authorized_with_task"  # 3. Авторизований, є відкрита задача


def get_user_bot_state(telegram_id: int) -> str:
    """Отримує поточний стан бота для користувача"""
    try:
        state = user_state_manager.load_user_state(telegram_id)
        if not state:
            logger.info(f"Користувач {telegram_id} не знайдений - стан: REGISTRATION")
            return BotState.REGISTRATION

        # Перевіряємо тип стану
        state_type = state.get("type", "")

        if state_type == "registration_in_progress":
            logger.info(
                f"Користувач {telegram_id} в процесі реєстрації - стан: REGISTRATION"
            )
            return BotState.REGISTRATION

        if state_type in ["user_profile", "registration_completed"]:
            # Користувач зареєстрований, перевіряємо наявність відкритих задач
            bot_state = state.get("bot_state", {})
            current_task = bot_state.get("current_task_key", "")

            if current_task:
                logger.info(
                    f"Користувач {telegram_id} має відкриту задачу {current_task} - стан: AUTHORIZED_WITH_TASK"
                )
                return BotState.AUTHORIZED_WITH_TASK
            else:
                logger.info(
                    f"Користувач {telegram_id} авторизований без відкритих задач - стан: AUTHORIZED_NO_TASKS"
                )
                return BotState.AUTHORIZED_NO_TASKS

        # За замовчуванням - реєстрація
        logger.warning(
            f"Невідомий стан користувача {telegram_id}: {state_type} - повертаємо REGISTRATION"
        )
        return BotState.REGISTRATION

    except Exception as e:
        logger.error(f"Помилка отримання стану користувача {telegram_id}: {e}")
        return BotState.REGISTRATION


def set_user_bot_state(telegram_id: int, bot_state: str, task_key: str = "") -> bool:
    """Встановлює стан бота для користувача"""
    try:
        # Завантажуємо поточний стан
        current_state = user_state_manager.load_user_state(telegram_id)
        if not current_state:
            logger.warning(
                f"Неможливо встановити стан бота для неіснуючого користувача {telegram_id}"
            )
            return False

        # Додаємо або оновлюємо bot_state
        if "bot_state" not in current_state:
            current_state["bot_state"] = {}

        current_state["bot_state"]["state"] = bot_state
        current_state["bot_state"]["last_updated"] = datetime.now().isoformat()

        if bot_state == BotState.AUTHORIZED_WITH_TASK and task_key:
            current_state["bot_state"]["current_task_key"] = task_key
        elif bot_state == BotState.AUTHORIZED_NO_TASKS:
            current_state["bot_state"]["current_task_key"] = ""

        # Зберігаємо оновлений стан
        result = user_state_manager.save_user_state(telegram_id, current_state)
        logger.info(
            f"Встановлено стан бота для користувача {telegram_id}: {bot_state} (задача: {task_key})"
        )
        return result

    except Exception as e:
        logger.error(
            f"Помилка встановлення стану бота для користувача {telegram_id}: {e}"
        )
        return False


def complete_user_registration_and_set_state(telegram_id: int) -> bool:
    """Завершує реєстрацію і встановлює стан AUTHORIZED_NO_TASKS"""
    try:
        # Спочатку завершуємо реєстрацію
        if complete_registration(telegram_id):
            # Потім встановлюємо стан бота
            return set_user_bot_state(telegram_id, BotState.AUTHORIZED_NO_TASKS)
        return False
    except Exception as e:
        logger.error(
            f"Помилка завершення реєстрації та встановлення стану для {telegram_id}: {e}"
        )
        return False


def set_user_current_task(telegram_id: int, task_key: str) -> bool:
    """Встановлює поточну задачу користувача та змінює стан на AUTHORIZED_WITH_TASK"""
    return set_user_bot_state(telegram_id, BotState.AUTHORIZED_WITH_TASK, task_key)


def clear_user_current_task(telegram_id: int) -> bool:
    """Очищає поточну задачу користувача та змінює стан на AUTHORIZED_NO_TASKS"""
    return set_user_bot_state(telegram_id, BotState.AUTHORIZED_NO_TASKS)


def get_user_current_task(telegram_id: int) -> str:
    """Отримує ключ поточної задачі користувача"""
    try:
        state = user_state_manager.load_user_state(telegram_id)
        if state and "bot_state" in state:
            return str(state["bot_state"].get("current_task_key", ""))
        return ""
    except Exception as e:
        logger.error(
            f"Помилка отримання поточної задачі користувача {telegram_id}: {e}"
        )
        return ""
