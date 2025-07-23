#!/usr/bin/env python3
"""
Сервіс для збереження та відновлення стану користувачів
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

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
                "state": state_data
            }
            
            with open(user_file, 'w', encoding='utf-8') as f:
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
            
            with open(user_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            logger.info(f"Завантажено стан користувача {telegram_id} з файлу {user_file}")
            return data.get("state", {})
            
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
                    telegram_id = int(filename.split('_')[1])
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
            
            with open(user_file, 'r', encoding='utf-8') as f:
                return json.load(f)
                
        except Exception as e:
            logger.error(f"Помилка отримання інформації про користувача {telegram_id}: {e}")
            return None

# Глобальний екземпляр менеджера
user_state_manager = UserStateManager()

def save_registration_state(telegram_id: int, registration_data: Dict[str, Any], registration_step: str) -> bool:
    """Зберігає стан реєстрації користувача"""
    state_data = {
        "registration": registration_data,
        "registration_step": registration_step,
        "type": "registration_in_progress"
    }
    return user_state_manager.save_user_state(telegram_id, state_data)

def load_registration_state(telegram_id: int) -> Optional[Dict[str, Any]]:
    """Завантажує стан реєстрації користувача (тільки активні реєстрації)"""
    state = user_state_manager.load_user_state(telegram_id)
    if state and state.get("type") == "registration_in_progress":
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
            "completed_at": datetime.now().isoformat()
        }
        
        # Зберігаємо оновлений стан
        result = user_state_manager.save_user_state(telegram_id, completed_state)
        logger.info(f"Реєстрацію користувача {telegram_id} позначено як завершену")
        return result
        
    except Exception as e:
        logger.error(f"Помилка завершення реєстрації користувача {telegram_id}: {e}")
        return False
