#!/usr/bin/env python3
"""
Гібридний сервіс управління користувачами.
Поєднує Google Sheets (основне сховище) з локальним кешем (файли JSON).
"""

import logging
import os
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

import logging
from typing import Dict, Any, Optional, Tuple
from src.google_sheets_service import (
    find_user_by_phone, 
    find_user_by_telegram_id, 
    update_user_telegram, 
    add_new_user,
    GoogleSheetsError
)
from src.user_state_service import (
    save_user_profile, 
    load_user_profile, 
    update_user_sync_status,
    list_all_cached_users
)

logger = logging.getLogger(__name__)

class UserManager:
    """Гібридний менеджер користувачів з Google Sheets та локальним кешем"""
    
    def __init__(self):
        self.google_available = True
        
    async def find_user_comprehensive(self, telegram_id: int, phone: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], str]:
        """
        Комплексний пошук користувача з різних джерел
        
        Returns:
            Tuple[user_data, source] где source може бути: 'google', 'cache', 'not_found'
        """
        user_data = None
        source = 'not_found'
        
        # 1. Спочатку перевіряємо локальний кеш
        cached_profile = load_user_profile(telegram_id)
        if cached_profile:
            logger.info(f"Користувач {telegram_id} знайдений в локальному кеші")
            
            # Спробуємо синхронізувати з Google Sheets для свіжих даних
            try:
                google_result = find_user_by_telegram_id(str(telegram_id))
                if google_result:
                    record, row = google_result
                    # Оновлюємо кеш свіжими даними з Google
                    save_user_profile(telegram_id, record, "active")
                    update_user_sync_status(telegram_id, True)
                    logger.info(f"Кеш користувача {telegram_id} оновлено з Google Sheets")
                    return record, 'google'
                else:
                    # Google не має цього користувача, але кеш є - спробуємо записати в Google
                    logger.warning(f"Користувач {telegram_id} є в кеші, але відсутній в Google Sheets")
                    try:
                        # Спробуємо відновити користувача в Google Sheets з кешу
                        row_num = add_new_user(cached_profile)
                        update_user_sync_status(telegram_id, True)
                        logger.info(f"✅ Користувача {telegram_id} відновлено в Google Sheets (рядок #{row_num})")
                        
                        # Повторно отримуємо з Google для синхронізації
                        google_result = find_user_by_telegram_id(str(telegram_id))
                        if google_result:
                            record, row = google_result
                            save_user_profile(telegram_id, record, "active")
                            return record, 'google'
                    except GoogleSheetsError as e:
                        logger.error(f"❌ Не вдалось відновити користувача {telegram_id} в Google Sheets: {e}")
                        update_user_sync_status(telegram_id, False)
                    
                    # Використовуємо кеш як резерв
                    return cached_profile, 'cache'
                    
            except GoogleSheetsError as e:
                logger.error(f"Помилка доступу до Google Sheets: {e}")
                self.google_available = False
                # Використовуємо кеш як резерв
                return cached_profile, 'cache'
        
        # 2. Якщо в кеші немає, перевіряємо Google Sheets
        try:
            # Пошук за Telegram ID
            google_result = find_user_by_telegram_id(str(telegram_id))
            if google_result:
                record, row = google_result
                # Зберігаємо в кеш для майбутнього використання
                save_user_profile(telegram_id, record, "active")
                logger.info(f"Користувач {telegram_id} знайдений в Google Sheets і збережений в кеш")
                return record, 'google'
            
            # Пошук за номером телефону (якщо надано)
            if phone:
                phone_result = find_user_by_phone(phone)
                if phone_result:
                    record, row = phone_result
                    # Зберігаємо в кеш
                    save_user_profile(telegram_id, record, "active")
                    logger.info(f"Користувач знайдений за номером {phone} в Google Sheets")
                    return record, 'google'
                    
        except GoogleSheetsError as e:
            logger.error(f"Помилка доступу до Google Sheets: {e}")
            self.google_available = False
            
        return None, 'not_found'
        
    async def authorize_user(self, telegram_id: int, phone: str) -> Tuple[Optional[Dict[str, Any]], str]:
        """
        Авторизує користувача за номером телефону
        
        Returns:
            Tuple[user_data, status] где status: 'authorized', 'need_registration', 'error'
        """
        try:
            # Пошук за номером телефону
            phone_result = find_user_by_phone(phone)
            if phone_result:
                record, row = phone_result
                
                # Оновлюємо Telegram дані в Google Sheets
                tg_username = ""  # Буде оновлено пізніше з update object
                update_user_telegram(row, str(telegram_id), tg_username)
                
                # Оновлюємо запис з новими Telegram даними
                record["telegram_id"] = str(telegram_id)
                record["mobile_number"] = phone
                
                # Зберігаємо в локальному кеші
                save_user_profile(telegram_id, record, "active")
                update_user_sync_status(telegram_id, True)
                
                logger.info(f"Користувач авторизований: {record.get('full_name')} (телефон: {phone})")
                return record, 'authorized'
            else:
                logger.info(f"Користувач з номером {phone} не знайдений в базі")
                return None, 'need_registration'
                
        except GoogleSheetsError as e:
            logger.error(f"Помилка авторизації користувача: {e}")
            self.google_available = False
            
            # Перевіряємо кеш як резерв
            all_cached = list_all_cached_users()
            for cached_user in all_cached:
                if cached_user.get("mobile_number") == phone:
                    logger.info(f"Користувач знайдений в локальному кеші за номером {phone}")
                    return cached_user, 'authorized'
                    
            return None, 'error'
    
    async def register_new_user(self, registration_data: Dict[str, Any]) -> Tuple[bool, str, int]:
        """
        Реєструє нового користувача
        
        Returns:
            Tuple[success, message, row_number]
        """
        telegram_id = int(registration_data.get("telegram_id", 0))
        
        try:
            # Спробуємо зберегти в Google Sheets
            row_num = add_new_user(registration_data)
            
            # Зберігаємо в локальному кеші
            save_user_profile(telegram_id, registration_data, "active")
            update_user_sync_status(telegram_id, True)
            
            logger.info(f"Новий користувач зареєстрований: {registration_data.get('full_name')} (рядок #{row_num})")
            return True, f"Користувача успішно зареєстровано (рядок #{row_num})", row_num
            
        except GoogleSheetsError as e:
            logger.error(f"Помилка реєстрації в Google Sheets: {e}")
            self.google_available = False
            
            # Зберігаємо тільки в локальному кеші
            if save_user_profile(telegram_id, registration_data, "active"):
                update_user_sync_status(telegram_id, False)
                logger.info(f"Користувач збережений тільки в локальному кеші через проблеми з Google Sheets")
                return True, "Користувача збережено в локальному кеші (синхронізація з Google Sheets буде виконана пізніше)", 0
            else:
                return False, "Помилка збереження користувача", 0
    
    def get_user_cache_info(self, telegram_id: int) -> Dict[str, Any]:
        """Повертає інформацію про стан кешу користувача"""
        try:
            user_info = load_user_profile(telegram_id)
            if user_info:
                return {
                    "cached": True,
                    "sync_status": user_info.get("sync_with_google", False),
                    "last_sync": user_info.get("last_sync", "Unknown"),
                    "status": user_info.get("status", "Unknown")
                }
            return {"cached": False}
        except Exception as e:
            logger.error(f"Помилка отримання інформації про кеш {telegram_id}: {e}")
            return {"cached": False, "error": str(e)}
    
    def sync_pending_users(self) -> Dict[str, Any]:
        """Синхронізує користувачів, які не синхронізовані з Google Sheets"""
        result = {"synced": 0, "failed": 0, "errors": []}
        
        if not self.google_available:
            logger.warning("Google Sheets недоступні для синхронізації")
            return result
            
        try:
            all_cached = list_all_cached_users()
            for user in all_cached:
                telegram_id = user.get("telegram_id")
                if telegram_id and not user.get("sync_with_google", True):  # Потребує синхронізації
                    try:
                        add_new_user(user)
                        update_user_sync_status(int(telegram_id), True)
                        result["synced"] += 1
                        logger.info(f"Синхронізовано користувача {telegram_id} з Google Sheets")
                    except GoogleSheetsError as e:
                        result["failed"] += 1
                        result["errors"].append(f"User {telegram_id}: {str(e)}")
                        logger.error(f"Не вдалось синхронізувати користувача {telegram_id}: {e}")
                        
        except Exception as e:
            logger.error(f"Помилка синхронізації: {e}")
            result["errors"].append(f"General sync error: {str(e)}")
            
        return result

# Глобальний екземпляр менеджера
user_manager = UserManager()
