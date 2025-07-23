# handlers.py

import os
import logging
import re
from typing import Dict, Any, Optional

from telegram import Update, ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ContextTypes, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, ConversationHandler, ApplicationHandlerStop
)

from src.google_sheets_service import (  
    find_user_by_phone,
    find_user_by_telegram_id, 
    update_user_telegram,
    add_new_user
)
from src.user_state_service import save_registration_state, load_registration_state, complete_registration
from src.services import (
    create_jira_issue,
    find_open_issues,
    find_done_issues,
    add_comment_to_jira,
    add_comment_with_file_reference_to_jira,
    JiraApiError,
    attach_file_to_jira,
    get_issue_status,
    get_issue_details,
    get_full_issue_info
)
from src.constants import (
    DIVISIONS, DEPARTMENTS, SERVICES,
    DIVISION_ID_MAPPINGS, DEPARTMENT_ID_MAPPINGS, SERVICE_ID_MAPPINGS,
    JIRA_FIELD_MAPPINGS, JIRA_FIELD_IDS
)
from src.field_mapping import FIELD_MAP
from src.keyboards import (
    main_menu_markup,
    contact_request_markup,
    failed_auth_markup,
    after_create_markup,
    service_selection_markup,
    confirm_issue_markup,
    my_issues_markup,
    issues_view_markup
)
from config.config import (
    JIRA_REPORTER_ACCOUNT_ID,
    JIRA_PROJECT_KEY,
    JIRA_ISSUE_TYPE
)

# Стани ConversationHandler
SERVICE, DESCRIPTION, CONFIRM, FULL_NAME, MOBILE_NUMBER, DIVISION, DEPARTMENT = range(7)

# Ініціалізуємо логер
logger = logging.getLogger(__name__)

# Глобальна функція для валідації номера телефону
def validate_phone_format(phone: str) -> tuple[bool, str]:
    """
    Перевіряє чи номер телефону має правильний український формат
    
    Повертає:
        tuple[bool, str]: (is_valid, error_message)
    """
    # Прибираємо всі пробіли та інші символи, крім + та цифр
    clean_phone = re.sub(r'[^\d+]', '', phone)
    
    # Перевіряємо чи введено взагалі щось схоже на номер
    if not clean_phone:
        return False, "Номер телефону не може бути пустим"
    
    # Перевіряємо чи є в тексті щось, крім цифр, пробілів, дефісів та +
    if re.search(r'[^\d\s\-\(\)\+]', phone):
        return False, "Номер може містити тільки цифри, пробіли, дефіси та знак +"
    
    # Перевіряємо формат +380XXXXXXXXX (код країни +380 + 9 цифр)
    if clean_phone.startswith('+380'):
        if len(clean_phone) != 13:
            return False, f"Номер має містити рівно 13 символів (+380 + 9 цифр), введено: {len(clean_phone)}"
        
        digits_part = clean_phone[4:]  # Частина після +380
        if not digits_part.isdigit():
            return False, "Після +380 мають йти тільки цифри"
        
        if len(digits_part) != 9:
            return False, f"Після +380 має бути рівно 9 цифр, введено: {len(digits_part)}"
            
        return True, ""
    
    # Або формат без + (380XXXXXXXXX)
    elif clean_phone.startswith('380'):
        if len(clean_phone) != 12:
            return False, f"Номер має містити рівно 12 цифр (380 + 9 цифр), введено: {len(clean_phone)}"
        
        digits_part = clean_phone[3:]  # Частина після 380
        if not digits_part.isdigit():
            return False, "Після 380 мають йти тільки цифри"
            
        if len(digits_part) != 9:
            return False, f"Після 380 має бути рівно 9 цифр, введено: {len(digits_part)}"
            
        return True, ""
    else:
        # Якщо номер не починається з +380 або 380
        if clean_phone.startswith('+'):
            return False, "Український номер має починатися з +380"
        else:
            return False, "Український номер має починатися з +380 або 380"

# Глобальная переменная для отслеживания статуса активных задач 
active_task_is_done = False

# Кнопки головного меню для перевірки у ConversationHandler
MAIN_MENU_BUTTONS = [
    "🆕 Створити задачу", "🧾 Мої задачі", "👤 Мій профіль", "🔄 Оновити статус задачі", 
    "🔄 Повторити /start", "🔄 Повторна авторизація", "ℹ️ Допомога"
]

def check_main_menu_button_and_exit(text: str, context, update) -> bool:
    """
    Перевіряє, чи є текст кнопкою головного меню, і якщо так - завершує ConversationHandler
    
    Returns:
        True якщо це кнопка головного меню (ConversationHandler завершено)
        False якщо це НЕ кнопка головного меню (продовжуємо обробку)
    """
    # Перевіряємо на None або порожній рядок
    if not text or text.strip() == "":
        return False
        
    if text in MAIN_MENU_BUTTONS:
        user_id = str(update.effective_user.id)
        logger.warning(f"Користувач {user_id} натиснув кнопку головного меню '{text}' в ConversationHandler - завершуємо conversation")
        
        # Очищаємо дані конверсації
        conversation_keys = ["full_name", "mobile_number", "division", "department", 
                           "service", "description", "attached_photo"]
        for key in conversation_keys:
            context.user_data.pop(key, None)
        
        return True
    
    return False


def check_required_objects(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                          require_message: bool = True, 
                          require_callback: bool = False) -> bool:
    """
    Helper function to check if required Telegram objects are present.
    Returns True if all required objects are available, False otherwise.
    """
    if not update.effective_user:
        logger.error("Missing effective_user in update")
        return False
        
    if context.user_data is None:
        logger.error("Missing user_data in context")
        return False
        
    if require_message and not update.message:
        logger.error("Missing message in update")
        return False
        
    if require_callback and not update.callback_query:
        logger.error("Missing callback_query in update")
        return False
        
    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обробник /start.
    Перевіряє авторизацію за Telegram ID та запитує контакт якщо потрібно.
    """
    # Type guards for required objects
    if not check_required_objects(update, context, require_message=True):
        return
        
    user_id = str(update.effective_user.id)
    context.user_data["telegram_id"] = user_id
    tg_username = update.effective_user.username or ""
    
    # Очищаємо попередні дані тільки при прямому введенні команди /start
    # (не при виклику через restart_handler)
    if (update.message.text and update.message.text == "/start" and 
        not context.user_data.get("profile")):
        context.user_data.clear()
        context.user_data["telegram_id"] = user_id
    
    # Спочатку завжди перевіряємо користувача в Google Sheets за Telegram ID
    logger.info(f"Шукаємо користувача за Telegram ID: {user_id}")
    res = find_user_by_telegram_id(user_id)
    
    if res:
        # Користувача знайдено за Telegram ID
        record, row = res
        logger.info(f"Користувача знайдено за Telegram ID: {record.get('full_name')}")
        
        # Оновлюємо telegram_username, якщо змінився
        if tg_username and tg_username != record.get("telegram_username", ""):
            update_user_telegram(row, user_id, tg_username)
            record["telegram_username"] = tg_username
        
        # Зберігаємо профіль
        context.user_data["profile"] = record
        
        # Показуємо спрощене вітання
        await update.message.reply_text(
            f"👋 *Вітаємо, {record['full_name']}!*",
            reply_markup=main_menu_markup,
            parse_mode="Markdown"
        )
    else:
        # Користувача не знайдено, запитуємо номер телефону для авторизації - спрощений текст
        logger.info(f"Користувача не знайдено за Telegram ID, запитуємо номер телефону")
        await update.message.reply_text(
            "👋 *Вітаємо в боті техпідтримки!*\n\n"
            "📱 *Натисніть кнопку щоб поділитися номером телефону:*",
            reply_markup=contact_request_markup,
            parse_mode="Markdown"
        )
        # Встановлюємо дані для нового користувача
        context.user_data["new_user"] = {
            "telegram_id": user_id,
            "telegram_username": tg_username
        }


async def global_contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глобальний обробник контакту для початкової авторизації з головного меню"""
    # Type guards for required objects
    if not update.message or not update.message.contact or not update.effective_user or not context.user_data:
        logger.error("Missing required objects in global contact handler")
        return
        
    contact = update.message.contact
    phone = contact.phone_number
    
    logger.info(f"Глобальна авторизація: отримано номер телефону {phone}")
    
    # Шукаємо користувача в Google Sheets
    res = find_user_by_phone(phone)
    if res:
        record, row = res
        # Оновлюємо telegram_id та username
        tg_id = str(update.effective_user.id)
        tg_username = update.effective_user.username or ""
        
        # Оновлюємо дані в таблиці
        update_user_telegram(row, tg_id, tg_username)
        
        # Зберігаємо профіль
        record["telegram_id"] = tg_id.strip().replace("'", "")
        record["telegram_username"] = tg_username
        record["mobile_number"] = phone
        account_id = record.get("account_id")
        if account_id:
            record["account_id"] = account_id
        context.user_data["profile"] = record
        
        await update.message.reply_text(
            f"✅ *Ви успішно авторизовані, {record['full_name']}!*",
            reply_markup=main_menu_markup,
            parse_mode="Markdown"
        )
        logger.info(f"Успішна глобальна авторизація для {record['full_name']}")
    else:
        # Номер не знайдено в базі - одразу переходимо до реєстрації
        await update.message.reply_text(
            "⚠️ Номер не знайдено в базі.\n\n"
            "Для реєстрації та створення задачі введіть ваше повне ім'я (ПІБ):",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )
        
        # Зберігаємо номер телефону для подальшого використання
        context.user_data["registration"] = {
            "phone": phone,
            "telegram_id": str(update.effective_user.id),
            "telegram_username": update.effective_user.username or ""
        }
        context.user_data["registration_step"] = "name"
        
        # Зберігаємо стан реєстрації у файл
        telegram_id = int(update.effective_user.id)
        save_registration_state(telegram_id, context.user_data["registration"], "name")
        
        logger.info(f"Почато розширену реєстрацію нового користувача з номером {phone}")


async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка отриманого контакту для авторизації всередині ConversationHandler"""
    # Type guards for required objects
    if not update.message or not update.message.contact or not update.effective_user or not context.user_data:
        logger.error("Missing required objects in conversation contact handler")
        return
        
    contact = update.message.contact
    phone = contact.phone_number
    
    # Сохраняем номер телефона в любом случае для возможного будущего создания пользователя
    context.user_data["mobile_number"] = phone
    logger.info(f"ConversationHandler: отримано номер телефону {phone}")
    
    # Шукаємо користувача в Google Sheets
    res = find_user_by_phone(phone)
    if res:
        record, row = res
        # Оновлюємо telegram_id та username
        tg_id = str(update.effective_user.id)
        tg_username = update.effective_user.username or ""
        
        # Оновлюємо дані в таблиці
        update_user_telegram(row, tg_id, tg_username)
        
        # Зберігаємо профіль
        record["telegram_id"] = tg_id.strip().replace("'", "")
        record["telegram_username"] = tg_username
        record["mobile_number"] = phone
        account_id = record.get("account_id")
        if account_id:
            record["account_id"] = account_id
        context.user_data["profile"] = record
        
        await update.message.reply_text(
            f"✅ *Ви успішно авторизовані, {record['full_name']}!*",
            reply_markup=main_menu_markup,
            parse_mode="Markdown"
        )
        
        # Перевіряємо, чи перебуваємо ми в процесі створення заявки
        if context.user_data.get("full_name"):
            # Ми в процесі створення заявки, переходимо до наступного кроку
            markup = ReplyKeyboardMarkup(
                [[div] for div in DIVISIONS] + [["🔙 Назад"]],
                resize_keyboard=True,
                one_time_keyboard=True
            )
            await update.message.reply_text(
                "*Оберіть ваш підрозділ:*",
                reply_markup=markup,
                parse_mode="Markdown"
            )
            return DIVISION
    else:
        # Не знайдено в базі - направляємо на розширену реєстрацію поза ConversationHandler
        await update.message.reply_text(
            "⚠️ *Номер не знайдено в базі.*\n\n"
            "Для реєстрації та створення задачі введіть ваше повне ім'я (ПІБ):",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )
        
        # Зберігаємо номер телефону для розширеної реєстрації
        context.user_data["registration"] = {
            "phone": phone,
            "telegram_id": str(update.effective_user.id),
            "telegram_username": update.effective_user.username or ""
        }
        context.user_data["registration_step"] = "name"
        
        # Зберігаємо стан реєстрації у файл
        telegram_id = int(update.effective_user.id)
        save_registration_state(telegram_id, context.user_data["registration"], "name")
        
        # ЗАВЕРШУЄМО ConversationHandler і переходимо до розширеної реєстрації
        logger.info(f"ConversationHandler: починаємо розширену реєстрацію для номера {phone}")
        return ConversationHandler.END


async def global_registration_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глобальний обробник для реєстрації нових користувачів поза ConversationHandler
    
    Примітка: Номер телефону в цьому обробнику завжди отримується через кнопку
    'Надати номер телефону', тому валідація не потрібна. Але функція validate_phone_format()
    доступна для майбутнього використання, якщо з'явиться потреба в ручному введенні номера.
    """
    # Отримуємо telegram_id користувача
    telegram_id = int(update.effective_user.id)
    
    # Спробуємо завантажити стан з файлу, якщо його немає в context
    registration_step = context.user_data.get("registration_step")
    if not registration_step:
        saved_state = load_registration_state(telegram_id)
        if saved_state and saved_state.get("state", {}).get("type") != "registration_completed":
            context.user_data["registration"] = saved_state["state"]["registration"]
            context.user_data["registration_step"] = saved_state["state"]["registration_step"]
            registration_step = saved_state["state"]["registration_step"]
            logger.info(f"Відновлено стан реєстрації з файлу: крок '{registration_step}'")
        elif saved_state and saved_state.get("state", {}).get("type") == "registration_completed":
            # Реєстрацію завершено, очищаємо файл і пропускаємо
            logger.info("Реєстрацію користувача вже завершено, очищаємо стан")
            complete_registration(telegram_id)
            raise ApplicationHandlerStop()
    
    # Якщо не в режимі реєстрації, пропускаємо управління далі
    if not registration_step:
        logger.info(f"Не в режимі реєстрації, завершуємо global_registration_handler для повідомлення: '{update.message.text}'")
        # Викидаємо ApplicationHandlerStop для передачі управління наступному handler
        raise ApplicationHandlerStop()
    
    if registration_step == "name":
        # Збираємо ПІБ
        full_name = update.message.text.strip()
        if not full_name or len(full_name) < 3:
            await update.message.reply_text(
                "❌ *Будь ласка, введіть коректне ПІБ* _(мінімум 3 символи)_:",
                parse_mode="Markdown"
            )
            return
        
        # Зберігаємо ПІБ і переходимо до підрозділу
        context.user_data["registration"]["full_name"] = full_name
        context.user_data["registration_step"] = "division"
        
        # Зберігаємо стан у файл
        save_registration_state(telegram_id, context.user_data["registration"], "division")
        
        # Запитуємо підрозділ
        markup = ReplyKeyboardMarkup(
            [[div] for div in DIVISIONS],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await update.message.reply_text(
            f"✅ *Дякуємо, {full_name}!*\n\n"
            "📍 *Оберіть ваш підрозділ:*",
            reply_markup=markup,
            parse_mode="Markdown"
        )
        
    elif registration_step == "division":
        # Збираємо підрозділ
        division = update.message.text.strip()
        if division not in DIVISIONS:
            await update.message.reply_text(
                "❌ *Будь ласка, оберіть підрозділ зі списку:*",
                parse_mode="Markdown"
            )
            return
        
        # Зберігаємо підрозділ і переходимо до департаменту
        context.user_data["registration"]["division"] = division
        context.user_data["registration_step"] = "department"
        
        # Зберігаємо стан у файл
        save_registration_state(telegram_id, context.user_data["registration"], "department")
        
        # Запитуємо департамент
        markup = ReplyKeyboardMarkup(
            [[dept] for dept in DEPARTMENTS],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await update.message.reply_text(
            f"📍 *Підрозділ: {division}*\n\n"
            "🏢 *Оберіть ваш департамент:*",
            reply_markup=markup,
            parse_mode="Markdown"
        )
        
    elif registration_step == "department":
        # Збираємо департамент
        department = update.message.text.strip()
        if department not in DEPARTMENTS:
            await update.message.reply_text(
                "❌ *Будь ласка, оберіть департамент зі списку:*",
                parse_mode="Markdown"
            )
            return
        
        # Зберігаємо департамент
        context.user_data["registration"]["department"] = department
        
        # Зберігаємо стан у файл
        save_registration_state(telegram_id, context.user_data["registration"], "confirm")
        
        # Показуємо підтвердження з усіма даними
        reg_data = context.user_data["registration"]
        confirmation_text = (
            "✅ *Підтвердіть ваші дані:*\n\n"
            f"👤 **ПІБ:** {reg_data['full_name']}\n"
            f"📱 **Телефон:** {reg_data['phone']}\n"
            f"📍 **Підрозділ:** {reg_data['division']}\n"
            f"🏢 **Департамент:** {reg_data['department']}\n\n"
            "*Все правильно?*"
        )
        
        # Кнопки підтвердження
        markup = ReplyKeyboardMarkup(
            [["Підтвердити"], ["❌ Скасувати"]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        
        logger.info(f"Показуємо підтвердження для користувача з даними: {reg_data}")
        await update.message.reply_text(
            confirmation_text,
            reply_markup=markup,
            parse_mode="Markdown"
        )
        
        context.user_data["registration_step"] = "confirm"
        logger.info("Перехід в режим підтвердження (confirm)")
        
    elif registration_step == "confirm":
        # Обробляємо підтвердження
        confirmation = update.message.text.strip()
        
        # 🔍 ДЕТАЛЬНЕ ЛОГУВАННЯ ДЛЯ ДІАГНОСТИКИ КНОПКИ
        logger.info(f"=== BUTTON DEBUG INFO ===")
        logger.info(f"Raw text: '{update.message.text}'")
        logger.info(f"Stripped text: '{confirmation}'")
        logger.info(f"Text length: {len(confirmation)}")
        logger.info(f"UTF-8 bytes: {confirmation.encode('utf-8')}")
        logger.info(f"Hex representation: {confirmation.encode('utf-8').hex()}")
        logger.info(f"Unicode codepoints: {[ord(c) for c in confirmation]}")
        logger.info(f"User ID: {update.effective_user.id}")
        logger.info(f"Chat ID: {update.effective_chat.id}")
        logger.info(f"Message ID: {update.message.message_id}")
        logger.info(f"=========================")
        
        logger.info(f"Отримано підтвердження: '{confirmation}'")
        
        if confirmation == "❌ Скасувати":
            # Скасовуємо реєстрацію
            context.user_data.pop("registration", None)
            context.user_data.pop("registration_step", None)
            
            # Видаляємо файл стану реєстрації
            complete_registration(telegram_id)
            
            await update.message.reply_text(
                "❌ *Реєстрацію скасовано.*\n\n"
                "Для створення задач вам потрібно буде пройти реєстрацію знову.",
                reply_markup=main_menu_markup,
                parse_mode="Markdown"
            )
        else:
            # Будь-який інший текст означає підтвердження
            # Зберігаємо користувача в Google Sheets
            try:
                reg_data = context.user_data["registration"]
                
                # Підготовуємо дані для Google Sheets
                new_user_data = {
                    "telegram_id": reg_data["telegram_id"],
                    "telegram_username": reg_data["telegram_username"],
                    "mobile_number": reg_data["phone"],
                    "full_name": reg_data["full_name"],
                    "division": reg_data["division"],
                    "department": reg_data["department"]
                }
                
                # Зберігаємо в Google Sheets
                from src.google_sheets_service import add_new_user
                row_num = add_new_user(new_user_data)
                
                # Зберігаємо профіль користувача в context
                context.user_data["profile"] = new_user_data
                context.user_data["full_name"] = reg_data["full_name"]
                context.user_data["mobile_number"] = reg_data["phone"]
                
                # Очищаємо дані реєстрації
                context.user_data.pop("registration", None)
                context.user_data.pop("registration_step", None)
                
                # Видаляємо файл стану реєстрації
                complete_registration(telegram_id)
                
                # Показуємо успішне завершення реєстрації
                await update.message.reply_text(
                    f"🎉 *Реєстрацію завершено успішно!*\n\n"
                    f"Ваші дані збережено в системі (рядок #{row_num}).\n"
                    f"Тепер ви можете створювати задачі та користуватися всіма функціями бота.",
                    reply_markup=main_menu_markup,
                    parse_mode="Markdown"
                )
                
                logger.info(f"Нового користувача {reg_data['full_name']} успішно зареєстровано та збережено в Google Sheets (рядок {row_num})")
                
            except Exception as e:
                logger.error(f"Помилка збереження нового користувача в Google Sheets: {e}")
                await update.message.reply_text(
                    "❌ *Помилка збереження даних.*\n\n"
                    "Спробуйте пізніше або зверніться до адміністратора.",
                    reply_markup=main_menu_markup,
                    parse_mode="Markdown"
                )
    else:
        # Не в режимі реєстрації - передаємо управління далі
        raise ApplicationHandlerStop()


async def my_profile_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник кнопки 'Мій профіль' - показує детальну інформацію користувача"""
    # Type guards for required objects
    if not check_required_objects(update, context, require_message=True):
        return
    
    profile = context.user_data.get("profile")
    if not profile or not profile.get("telegram_id"):
        await update.message.reply_text(
            "❗ *Ви не авторизовані.*\n"
            "Для перегляду профілю необхідна авторизація за номером телефону.",
            reply_markup=contact_request_markup,
            parse_mode="Markdown"
        )
        return
    
    # Формуємо детальну інформацію про користувача
    user_info = f"👤 *Ваш профіль:*\n\n"
    user_info += f"👤 *Ім'я:* {profile['full_name']}\n"
    user_info += f"📱 *Телефон:* {profile.get('mobile_number', 'Не вказано')}\n"
    user_info += f"📧 *Email:* {profile.get('email', 'Не вказано')}\n"
    user_info += f"🏢 *Відділ:* {profile.get('department', 'Не вказано')}\n"
    # user_info += f"🎯 *Посада:* {profile.get('position', 'Не вказано')}\n"

    # # Додаємо статус підключення до Jira
    # if profile.get('account_id'):
    #     user_info += f"✅ *Jira:* Підключено\n"
    # else:
    #     user_info += f"❌ *Jira:* Не підключено\n"
    
    user_info += f"\n🆔 *Telegram ID:* `{profile['telegram_id']}`"
    
    await update.message.reply_text(
        user_info,
        reply_markup=main_menu_markup,
        parse_mode="Markdown"
    )


async def re_auth_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник кнопки 'Повторна авторизація'"""
    # Type guards for required objects
    if not check_required_objects(update, context, require_message=True):
        return
    
    # Очищаємо профіль і дані користувача для повторної авторизації
    context.user_data.clear()
    user_id = str(update.effective_user.id)
    tg_username = update.effective_user.username or ""
    context.user_data["telegram_id"] = user_id
    
    await update.message.reply_text(
        "🔄 *Повторна авторизація*\n\n"
        "Для повторної авторизації надішліть ваш номер телефону:",
        reply_markup=contact_request_markup,
        parse_mode="Markdown"
    )


async def restart_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник кнопки 'Повторити /start' - виконує рестарт зі збереженням профілю"""
    # Type guards for required objects
    if not check_required_objects(update, context, require_message=True):
        return
    
    # Зберігаємо профіль користувача перед рестартом
    saved_profile = context.user_data.get("profile")
    
    # Очищаємо дані користувача, але зберігаємо профіль
    context.user_data.clear()
    user_id = str(update.effective_user.id)
    context.user_data["telegram_id"] = user_id
    
    # Відновлюємо профіль, якщо він був
    if saved_profile:
        context.user_data["profile"] = saved_profile
    
    # Викликаємо функцію start напряму замість відправки команди
    await start(update, context)


async def create_task_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Простий обробник кнопки 'Створити задачу' для запуску ConversationHandler"""
    logger.info(f"create_task_button_handler: отримано текст '{update.message.text}'")
    
    # Перенаправляємо на create_issue_start
    return await create_issue_start(update, context)


async def continue_without_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник кнопки 'Продовжити без авторизації'"""
    # Встановлюємо початкові дані для нового користувача
    tg_id = str(update.effective_user.id)
    tg_username = update.effective_user.username or ""
    mobile_number = context.user_data.get("mobile_number", "")
    
    # Встановлюємо початкові дані для неавторизованого користувача
    context.user_data["profile"] = None
    context.user_data["telegram_id"] = tg_id
    context.user_data["telegram_username"] = tg_username
    if mobile_number:
        context.user_data["mobile_number"] = mobile_number
    
    # Перевіряємо, чи перебуваємо в процесі створення заявки
    if context.user_data.get("full_name"):
        # Якщо так, то переходимо до наступного кроку
        markup = ReplyKeyboardMarkup(
            [[div] for div in DIVISIONS] + [["🔙 Назад"]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await update.message.reply_text(
            "*Оберіть ваш підрозділ:*",
            reply_markup=markup,
            parse_mode="Markdown"
        )
        return DIVISION
    else:
        # Інакше просто показуємо головне меню
        await update.message.reply_text(
            "👤 *Ви продовжуєте без авторизації.* _При створенні задачі "
            "вам потрібно буде вказати ваші контактні дані.\n"
            "Ваші дані буде збережено для майбутніх звернень._",
            reply_markup=main_menu_markup,
            parse_mode="Markdown"
        )


async def my_issues(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показати список моїх відкритих задач у текстовому форматі"""
    profile = context.user_data.get("profile")
    user_id = str(update.effective_user.id)
    username = update.effective_user.username or "немає"
    
    # Розширене логування
    logger.info(f"my_issues: користувач ID={user_id}, username=@{username}")
    
    # Отримуємо telegram_id користувача з різних джерел
    telegram_id = None
    
    # 1. Спочатку спробуємо взяти з профілю
    if (profile and profile.get("telegram_id")):
        telegram_id = str(profile.get("telegram_id")).strip().replace("'", "")  # Нормалізуємо ID
        logger.info(f"my_issues: взято ID з профілю: {telegram_id}")
    # 2. Інакше використовуємо ID поточного користувача
    else:
        telegram_id = user_id.strip().replace("'", "")  # Нормалізуємо ID
        logger.info(f"my_issues: використовуємо ID з поточного повідомлення: {telegram_id}")
    
    # Показуємо нову клавіатуру для режиму перегляду задач
    await update.message.reply_text(
        "_Завантажую список ваших задач..._",
        reply_markup=issues_view_markup,
        parse_mode="Markdown"
    )
    
    # Отримуємо список задач
    try:
        # Використовуємо фактичний telegram_id для пошуку
        issues = await find_open_issues(telegram_id)
        logger.info(f"my_issues: знайдено {len(issues)} задач для ID {telegram_id}")
        
        for issue in issues:
            logger.info(f"my_issues: задача {issue['key']} зі статусом {issue['status']}")
    except Exception as e:
        logger.error(f"my_issues: помилка при пошуку задач для {telegram_id}: {str(e)}")
        issues = []
    if not issues:
        await update.message.reply_text(
            "*У вас немає відкритих задач.* _Ви можете створити нову задачу, натиснувши кнопку '🆕 Створити задачу'._",
            reply_markup=main_menu_markup,
            parse_mode="Markdown"
        )
        return
    
    # Зберігаємо список задач у контексті для можливості оновлення
    context.user_data["last_issues_list"] = issues
    
    # Вибираємо першу задачу як активну
    if len(issues) > 0:
        context.user_data["active_task"] = issues[0]["key"]
        logger.info(f"my_issues: встановлено активну задачу {issues[0]['key']}")
    
    # Формуємо текст зі списком задач
    text_list = ["*Ваші відкриті задачі:*"]
    for idx, issue in enumerate(issues, 1):
        active_mark = "➡️ " if issue["key"] == context.user_data.get("active_task") else ""
        text_list.append(f"{active_mark}*`{issue['key']}`* — _{issue['status']}_")
    
    text_list.append("\n_Щоб додати коментар до активної задачі, просто напишіть текст._")
    
    # Виводимо список з форматуванням Markdown
    await update.message.reply_text("\n".join(text_list), reply_markup=issues_view_markup, parse_mode="Markdown")
    
    # Викликаємо функцію для показу детальної інформації про активну задачу
    await show_active_task_details(update, context)


async def update_issues_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Оновлює список задач користувача"""
    profile = context.user_data.get("profile")
    tg_id = str(update.effective_user.id)
    
    # Отримуємо telegram_id користувача з різних джерел
    if profile and profile.get("telegram_id"):
        tg_id = str(profile.get("telegram_id"))
        logger.info(f"update_issues_status: взято ID з профілю: {tg_id}")
    else:
        logger.info(f"update_issues_status: використовуємо ID з поточного повідомлення: {tg_id}")
    
    # Повідомляємо про початок оновлення
    await update.message.reply_text("🔄 Оновлюю статуси задач...")
    
    try:
        # Перевіряємо, чи є активна задача в контексті
        active_task = context.user_data.get("active_task")
        
        # Отримуємо список активних та виконаних задач
        open_issues = await find_open_issues(tg_id)
        done_issues = await find_done_issues(tg_id)
        
        # Инициализируем переменную
        active_task_is_done = False
        
        # Якщо є активна задача в контексті, перевіряємо чи вона не стала Done
        if active_task:
            active_task_is_done = any(issue["key"] == active_task for issue in done_issues)
            if active_task_is_done:
                # Виводимо спеціальне повідомлення для виконаної задачі
                done_issue = next((issue for issue in done_issues if issue["key"] == active_task), None)
                
                # Надсилаємо два повідомлення для гарантованої зміни клавіатури
                await update.message.reply_text(
                    f"*Статуси оновлено. Ваша задача:*\n➡️ *`{active_task}`* — *Виконана*.\n\n"
                    f"*Можете створити нову задачу, натиснувши відповідну кнопку в меню:*",
                    parse_mode="Markdown"
                )
                
                # Надсилаємо додаткове повідомлення з клавіатурою головного меню
                await update.message.reply_text(
                    "🏠 *Головне меню*",
                    reply_markup=main_menu_markup,
                    parse_mode="Markdown"
                )
                
                # Очищаємо активну задачу
                context.user_data.pop("active_task", None)
                return
        
        # Якщо задач немає в API, але є активна задача в контексті (тільки що створена)
        if not open_issues and active_task and not active_task_is_done:
            await update.message.reply_text(
                f"Задача `{active_task}` ще не відображається в системі. Спробуйте оновити статус через кілька хвилин.",
                reply_markup=issues_view_markup,
                parse_mode="Markdown"
            )
            return
        # Якщо задач немає взагалі
        elif not open_issues:
            await update.message.reply_text(
                "*У вас немає відкритих задач.* _Ви можете створити нову задачу, натиснувши кнопку '🆕 Створити задачу'._",
                reply_markup=main_menu_markup,
                parse_mode="Markdown"
            )
            return
        
        # Зберігаємо оновлений список
        context.user_data["last_issues_list"] = open_issues
        
        # Вибираємо першу задачу як активну
        if len(open_issues) > 0:
            context.user_data["active_task"] = open_issues[0]["key"]
        
        # Формуємо текст зі списком задач
        text_list = ["*Ваша відкрита задача:*"]
        for idx, issue in enumerate(open_issues, 1):
            active_mark = "➡️ " if issue["key"] == context.user_data.get("active_task") else ""
            text_list.append(f"{active_mark}*`{issue['key']}`* — _{issue['status']}_")
        
        text_list.append("\n_Щоб додати коментар до активної задачі, просто напишіть текст._")
        
        # Виводимо список з форматуванням Markdown
        await update.message.reply_text("\n".join(text_list), 
                                      reply_markup=issues_view_markup,
                                      parse_mode="Markdown")
        
        # Викликаємо функцію для показу детальної інформації про активну задачу
        if not await show_active_task_details(update, context):
            logger.error(f"Не вдалося показати деталі задачі")
            await update.message.reply_text(
                "❌ *Не вдалося отримати деталі задачі. Будь ласка, спробуйте ще раз.*",
                reply_markup=issues_view_markup,
                parse_mode="Markdown"
            )
    
    except Exception as e:
        logger.error(f"Помилка при оновленні статусів задач: {str(e)}")
        await update.message.reply_text(
            f"❌ *Помилка при оновленні статусів:* _{str(e)}_",
            reply_markup=issues_view_markup,
            parse_mode="Markdown"
        )


async def return_to_main_from_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник для кнопки 'Вийти на головну' з ConversationHandler"""
    # Очищаємо дані конверсації
    context.user_data.pop("full_name", None)
    context.user_data.pop("mobile_number", None)
    context.user_data.pop("division", None)
    context.user_data.pop("department", None)
    context.user_data.pop("service", None)
    context.user_data.pop("description", None)
    context.user_data.pop("attached_photo", None)
    
    await update.message.reply_text("🏠 *Головне меню*", reply_markup=main_menu_markup, parse_mode="Markdown")
    return ConversationHandler.END


async def return_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник для кнопки 'Вийти на головну' з режиму перегляду задач"""
    # Очищаємо непотрібні дані
    if context.user_data and "last_issues_list" in context.user_data:
        del context.user_data["last_issues_list"]
    
    await update.message.reply_text("🏠", reply_markup=main_menu_markup, parse_mode="Markdown")


async def back_to_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник для інлайн-кнопки 'Вийти на головну'"""
    await update.callback_query.answer()
    
    # Очищаємо непотрібні дані
    if context.user_data and "last_issues_list" in context.user_data:
        del context.user_data["last_issues_list"]

    await update.callback_query.message.reply_text("🏠", reply_markup=main_menu_markup, parse_mode="Markdown")


async def issue_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Користувач вибрав задачу для коментування"""
    data = update.callback_query.data  # формат ISSUE_<KEY>
    key = data.split("_", 1)[1]
    context.user_data["active_task"] = key
    await update.callback_query.answer()
    
    try:
        # Використовуємо функцію show_active_task_details для показу детальної інформації
        # Адаптуємо callback update для show_active_task_details
        await show_active_task_details(update, context)
        
    except Exception as e:
        logger.error(f"Помилка отримання деталей задачі {key}: {str(e)}")
        await update.callback_query.message.reply_text(
            f"❌ *Помилка отримання деталей задачі* `{key}`. _Спробуйте знову._",
            reply_markup=issues_view_markup,
            parse_mode="Markdown"
        )


async def comment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Автоматично додає коментар до відкритої задачі"""
    logger.info(f"comment_handler викликано! Текст повідомлення: '{update.message.text}'")
    
    # Перевіряємо, чи це не кнопка
    text = update.message.text
    logger.info(f"comment_handler: перевіряємо текст: '{text}'")
    
    if text in ["🧾 Мої задачі", "🆕 Створити задачу", "ℹ️ Допомога", "🔄 Повторити /start", 
                "🔄 Оновити статус задачі", "🏠 Вийти на головну", "✅ Перевірити статус задачі"]:
        # Це кнопка, пропускаємо
        logger.info(f"comment_handler: це кнопка, пропускаємо обробку")
        raise ApplicationHandlerStop()
    
    logger.info(f"comment_handler: це не кнопка, продовжуємо обробку коментаря")
    
    # Перевіряємо, чи користувач має відкриті задачі
    tg_id = str(update.effective_user.id)
    open_issues = await find_open_issues(tg_id)
    
    if not open_issues:
        await update.message.reply_text(
            "У вас немає відкритих задач. Ви можете створити нову задачу, натиснувши кнопку '🆕 Створити задачу'.",
            reply_markup=main_menu_markup,
            parse_mode="Markdown"
        )
        return
    
    # Автоматично встановлюємо першу відкриту задачу як активну
    key = open_issues[0]["key"]
    context.user_data["active_task"] = key
    logger.info(f"Автоматично встановлено активну задачу: {key}")

    if not text or text.strip() == "":
        await update.message.reply_text(
            "❌ *Коментар не може бути пустим.*",
            reply_markup=issues_view_markup,
            parse_mode="Markdown"
        )
        return

    try:
        # Отримуємо ПІБ користувача з профілю або conversation data
        author_name = None
        profile = context.user_data.get("profile")
        if profile and profile.get("full_name"):
            author_name = profile.get("full_name")
            logger.info(f"ПІБ отримано з профілю: {author_name}")
        else:
            # Якщо немає профілю, спробуємо взяти з conversation data
            author_name = context.user_data.get("full_name")
            if author_name:
                logger.info(f"ПІБ отримано з conversation data: {author_name}")
        
        # Якщо немає в контексті, спробуємо отримати з Google Sheets
        if not author_name:
            try:
                tg_id = str(update.effective_user.id)
                from src.google_sheets_service import find_user_by_telegram_id
                user_record = find_user_by_telegram_id(tg_id)
                if user_record and user_record[0]:
                    full_name = user_record[0].get("full_name")
                    author_name = str(full_name) if full_name is not None else None
                    logger.info(f"ПІБ отримано з Google Sheets: {author_name}")
            except Exception as e:
                logger.warning(f"Не вдалось отримати ПІБ з Google Sheets: {e}")
        
        logger.info(f"Додавання коментаря до задачі {key} від {author_name or 'невідомого користувача'}: '{text[:20]}...'")
        await add_comment_to_jira(key, text, author_name)
        
        # Додаємо повідомлення до кешу, щоб уникнути дублікатів при отриманні вебхуку
        from src.jira_webhooks2 import add_message_to_cache
        formatted_message = text
        add_message_to_cache(key, formatted_message)
        
        await update.message.reply_text(
            f"✅ Коментар додано до задачі *{key}*.\n_Ви можете продовжити додавати коментарі або прикріпити файл._", 
            reply_markup=issues_view_markup,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Помилка додавання коментаря до {key}: {str(e)}")
        await update.message.reply_text(
            f"❌ *Помилка додавання коментаря до задачі {key}*:\n_{str(e)}_",
            reply_markup=issues_view_markup,
            parse_mode="Markdown"
        )


async def file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробляє будь-яке вкладення і прикріплює до активної задачі"""
    key = context.user_data.get("active_task")
    if not key:
        await update.message.reply_text("❗ *Спершу створіть або виберіть задачу.*", reply_markup=issues_view_markup, parse_mode="Markdown")
        return

    # Перевірка на наявність файлу
    if update.message.document:
        file = update.message.document
        filename = file.file_name
    elif update.message.photo:
        file = update.message.photo[-1]
        filename = f"photo_{file.file_unique_id}.jpg"
    elif update.message.video:
        file = update.message.video
        filename = f"video_{file.file_unique_id}.mp4"
    elif update.message.audio:
        file = update.message.audio
        filename = f"audio_{file.file_unique_id}.mp3"
    else:
        await update.message.reply_text("❌ *Невідомий тип файлу.*", reply_markup=issues_view_markup, parse_mode="Markdown")
        return
    
    # Завжди використовуємо issues_view_markup для файлів
    reply_markup = issues_view_markup
    
    try:
        # Отримуємо файл
        tg_file = await file.get_file()
        # Завантажуємо файл в байти
        file_bytes = await tg_file.download_as_bytearray()
        
        # Отримуємо ПІБ користувача з профілю або conversation data
        author_name = None
        profile = context.user_data.get("profile")
        if profile and profile.get("full_name"):
            author_name = profile.get("full_name")
        else:
            # Якщо немає профілю, спробуємо взяти з conversation data
            author_name = context.user_data.get("full_name")
        
        # Якщо ПІБ все ще не знайдено, спробуємо отримати з Google Sheets
        if not author_name:
            try:
                from src.google_sheets_service import find_user_by_telegram_id
                user_id = str(update.effective_user.id)
                user_record = find_user_by_telegram_id(user_id)
                if user_record and user_record[0]:
                    author_name = user_record[0].get("full_name")
                    logger.info(f"ПІБ отримано з Google Sheets для файлу: {author_name}")
            except Exception as e:
                logger.warning(f"Не вдалось отримати ПІБ з Google Sheets для файлу: {e}")
        
        # Ensure author_name is either a string or None before passing to add_comment_to_jira
        author_name_str = str(author_name) if author_name is not None else None
        
        # Перевіряємо наявність тексту в повідомленні
        caption = update.message.caption
        
        # Якщо є підпис до файлу - спочатку додаємо коментар з текстом
        if caption and caption.strip():
            await add_comment_to_jira(key, caption.strip(), author_name_str)
            logger.info(f"Коментар з текстом від {author_name_str} додано до {key}")
            
            # Додаємо до кешу (simplified without tech support header)
            from src.jira_webhooks2 import add_message_to_cache
            formatted_message = caption.strip()
            add_message_to_cache(key, formatted_message)
        
        # Потім додаємо файл з посиланням в одному коментарі
        file_comment = ""  # Порожній текст, але заголовок автора буде додано автоматично
        await add_comment_with_file_reference_to_jira(key, file_comment, author_name_str, filename, bytes(file_bytes))
        logger.info(f"Коментар з файлом та посиланням від {author_name_str} додано до {key}")
        
        # Додаємо інформацію про файл до кешу (simplified without tech support header)
        from src.jira_webhooks2 import add_message_to_cache
        formatted_file_message = f"Прикріплено файл: {filename}"
        add_message_to_cache(key, formatted_file_message)
        
        # Повідомляємо користувача про успішне прикріплення
        if caption and caption.strip():
            await update.message.reply_text(
                f"✅ Коментар і файл '`{filename}`' з посиланням додано до *{key}*.", 
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            logger.info(f"Коментар з текстом і файл '{filename}' з посиланням успішно додано до задачі {key}")
        else:
            await update.message.reply_text(
                f"✅ Файл '`{filename}`' з посиланням прикріплено до *{key}*.", 
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            logger.info(f"Файл '{filename}' з посиланням успішно додано до задачі {key}")
        
    except Exception as e:
        error_message = str(e)
        logger.error(f"Помилка при прикріпленні файлу до {key}: {error_message}")
        await update.message.reply_text(f"❌ *Помилка:* файл не відправлено. _{error_message}_", 
                                      reply_markup=reply_markup,
                                      parse_mode="Markdown")


async def check_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Перевірити статус активної задачі"""
    key = context.user_data.get("active_task")
    if not key:
        await update.message.reply_text("❗ *Немає активної задачі.*", reply_markup=issues_view_markup, parse_mode="Markdown")
        return
        
    try:
        # Отримуємо повні деталі задачі з Jira
        issue = await get_full_issue_info(key)
        
        # Перевіряємо, чи задача виконана (статус Done)
        if issue.get('status', '').lower() == 'done' or issue.get('statusCategory', '').lower() == 'done':
            # Якщо задача виконана, показуємо відповідне повідомлення і повертаємо до головного меню
            await update.message.reply_text(
                f"*Статуси оновлено. Ваша задача:*\n➡️ *`{key}`* — *Виконана*.\n\n"
                f"*Можете створити нову задачу, натиснувши відповідну кнопку в меню:*",
                parse_mode="Markdown"
            )
            
            # Надсилаємо додаткове повідомлення з клавіатурою головного меню
            await update.message.reply_text(
                "🏠 *Головне меню*",
                reply_markup=main_menu_markup,
                parse_mode="Markdown"
            )
            
            # Очищаємо активну задачу
            context.user_data.pop("active_task", None)
            return
        
        # Используем модуль форматирования для единообразного отображения
        from fixed_issue_formatter import format_issue_info, format_issue_text
        
        # Получаем отформатированные данные
        formatted_issue = format_issue_info(issue)
        
        # Формируем текст и добавляем защиту от разбивки на символы
        text = format_issue_text(formatted_issue)
        
        # Добавляем маркер невидимого пробела в начало текста, чтобы предотвратить разбиение на символы
        text = '\u200B' + text
        
        logger.info(f"Перевірка статусу задачі {key}: {issue.get('status', 'Невідомо')}")
        await update.message.reply_text(
            text,
            reply_markup=issues_view_markup,
            parse_mode=None  # Отключаем парсинг Markdown/HTML для предотвращения проблем с форматированием
        )
    except Exception as e:
        logger.error(f"Помилка отримання статусу задачі {key}: {str(e)}")
        await update.message.reply_text(
            f"❌ *Помилка отримання статусу задачі* `{key}`.",
            reply_markup=issues_view_markup,
            parse_mode="Markdown"
        )


async def create_issue_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Початок створення задачі"""
    logger.info(f"create_issue_start викликано! Текст повідомлення: '{update.message.text}'")
    
    # Додаткова перевірка на точний текст
    if update.message.text != "🆕 Створити задачу":
        logger.warning(f"create_issue_start викликано з неочікуваним текстом: '{update.message.text}'")
        return ConversationHandler.END

    profile = context.user_data.get("profile")
    tg_id = str(update.effective_user.id)
    logger.info(f"create_issue_start: tg_id={tg_id}")

    # Перевірка на відкриті задачі
    open_issues = await find_open_issues(tg_id)
    if open_issues:
        key = open_issues[0]["key"]
        status = open_issues[0]["status"]
        await update.message.reply_text(
            f"У вас є відкрита задача *`{key}`* (статус: _{status}_).\n"
            "_Спочатку дочекайтесь її вирішення або додайте коментар до існуючої._",
            reply_markup=issues_view_markup,
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    # Якщо користувач авторизований - беремо дані з профілю та переходимо одразу до вибору сервісу
    if profile and profile.get("division") and profile.get("department"):
        # Копируем все необходимые данные из профиля пользователя
        context.user_data.update({
            "full_name": profile["full_name"],
            "division": profile["division"],
            "department": profile["department"],
            "mobile_number": profile.get("mobile_number", ""),
            "telegram_id": profile["telegram_id"],
            "telegram_username": profile.get("telegram_username", ""),
            "account_id": profile.get("account_id")
        })
        logger.info(f"Авторизований користувач {profile['full_name']} з повними даними, переходимо до вибору сервісу")

        # Переходимо до вибору сервісу напряму
        await update.message.reply_text(
            "*Оберіть сервіс:*",
            reply_markup=service_selection_markup(SERVICES),
            parse_mode="Markdown"
        )
        return SERVICE
    elif profile:
        # Користувач авторизований, але в нього неповні дані - доповнюємо їх
        logger.info(f"Авторизований користувач {profile['full_name']}, але потрібно доповнити дані профілю")
        context.user_data.update({
            "full_name": profile["full_name"],
            "mobile_number": profile.get("mobile_number", ""),
            "telegram_id": profile["telegram_id"],
            "telegram_username": profile.get("telegram_username", ""),
            "account_id": profile.get("account_id")
        })

        # Перевіряємо що саме відсутнє
        if not profile.get("division"):
            await update.message.reply_text(
                "*Оберіть ваш підрозділ:*",
                reply_markup=ReplyKeyboardMarkup(
                    [[div] for div in DIVISIONS] + [["🔙 Назад"]],
                    resize_keyboard=True,
                    one_time_keyboard=True
                ),
                parse_mode="Markdown"
            )
            return DIVISION
        elif not profile.get("department"):
            context.user_data["division"] = profile["division"]
            await update.message.reply_text(
                "*Оберіть ваш департамент:*",
                reply_markup=ReplyKeyboardMarkup(
                    [[dept] for dept in DEPARTMENTS] + [["🔙 Назад"]],
                    resize_keyboard=True,
                    one_time_keyboard=True
                ),
                parse_mode="Markdown"
            )
            return DEPARTMENT
    else:
        # Для неавторизованого користувача - спочатку запитуємо ПІБ
        markup = ReplyKeyboardMarkup(
            [["🏠 Вийти на головну"]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await update.message.reply_text(
            "*Будь ласка, введіть ваше повне ім'я:*",
            reply_markup=markup,
            parse_mode="Markdown"
        )
        logger.info(f"Переход к FULL_NAME для неавторизованого tg_id={tg_id}")
        return FULL_NAME


async def full_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка введеного ПІБ для неавторизованого користувача"""
    full_name = update.message.text.strip()
    tg_id = str(update.effective_user.id)
    logger.info(f"full_name_handler вызван, получено имя: '{full_name}', tg_id={tg_id}")
    
    # 🔍 КРИТИЧНА ПЕРЕВІРКА: Якщо отримали кнопку з головного меню, завершуємо ConversationHandler
    if check_main_menu_button_and_exit(full_name, context, update):
        await update.message.reply_text(
            "🔄 *Повернення до головного меню*\n\n"
            "Для створення нової задачі натисніть *'🆕 Створити задачу'*.",
            reply_markup=main_menu_markup,
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    
    if len(full_name) < 2:
        await update.message.reply_text(
            "❌ *Ім'я занадто коротке.* _Будь ласка, введіть ваше повне ім'я:_",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )
        return FULL_NAME
        
    context.user_data["full_name"] = full_name
    logger.info(f"Збережено ім'я користувача: {full_name}")
    
    # Запитуємо номер телефону
    await update.message.reply_text(
        "*Будь ласка, введіть ваш номер телефону* _у форматі +380XXXXXXXXX або натисніть кнопку 'Надати номер телефону':_",
        reply_markup=contact_request_markup,
        parse_mode="Markdown"
    )
    logger.info(f"Перехід до MOBILE_NUMBER для tg_id={tg_id}")
    return MOBILE_NUMBER

async def mobile_number_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка введеного номера телефону"""
    mobile_number = update.message.text.strip()
    tg_id = str(update.effective_user.id)
    logger.info(f"mobile_number_handler викликано, отримано номер: '{mobile_number}', tg_id={tg_id}")
    
    # 🔍 КРИТИЧНА ПЕРЕВІРКА: Якщо отримали кнопку з головного меню, завершуємо ConversationHandler
    if check_main_menu_button_and_exit(mobile_number, context, update):
        await update.message.reply_text(
            "🔄 *Повернення до головного меню*\n\n"
            "Для створення нової задачі натисніть *'🆕 Створити задачу'*.",
            reply_markup=main_menu_markup,
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    
    # Валідація: перевіряємо формат тільки для введених з клавіатури номерів
    # Номери отримані через кнопку "Надати номер телефону" завжди валідні
    is_from_keyboard = not (update.message.contact is not None)
    
    if is_from_keyboard:
        is_valid, error_message = validate_phone_format(mobile_number)
        if not is_valid:
            await update.message.reply_text(
                f"❌ *Некоректний формат номера телефону*\n\n"
                f"🚫 **Помилка:** {error_message}\n\n"
                f"📱 *Правильний формат:* `+380XXXXXXXXX`\n"
                f"💡 *Приклад:* `+380123456789`\n\n"
                f"_Або натисніть кнопку 'Надати номер телефону' для автоматичного надання._",
                reply_markup=contact_request_markup,
                parse_mode="Markdown"
            )
            return MOBILE_NUMBER
    
    # Зберігаємо номер телефону
    context.user_data["mobile_number"] = mobile_number
    
    # Переходимо до вибору підрозділу
    markup = ReplyKeyboardMarkup(
        [[div] for div in DIVISIONS] + [["🔙 Назад"]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await update.message.reply_text(
        "*Оберіть ваш підрозділ:*",
        reply_markup=markup,
        parse_mode="Markdown"
    )
    logger.info(f"Перехід до DIVISION для tg_id={tg_id}")
    return DIVISION

async def division_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка вибраного підрозділу"""
    text = update.message.text
    
    # 🔍 КРИТИЧНА ПЕРЕВІРКА: Якщо отримали кнопку з головного меню, завершуємо ConversationHandler
    if text and check_main_menu_button_and_exit(text, context, update):
        await update.message.reply_text(
            "🔄 *Повернення до головного меню*\n\n"
            "Для створення нової задачі натисніть *'🆕 Створити задачу'*.",
            reply_markup=main_menu_markup,
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    
    # Обробка кнопки "🔙 Назад"
    if text == "🔙 Назад":
        # Повертаємо на головний екран і завершуємо ConversationHandler
        await update.message.reply_text(
            "🏠 *Головне меню*",
            reply_markup=main_menu_markup,
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    
    # Перевірка наявності збереженого імені
    if not context.user_data.get("full_name"):
        await update.message.reply_text(
            "*Будь ласка, спочатку введіть ваше повне ім'я:*",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )
        return FULL_NAME
    
    context.user_data["division"] = text
    logger.info(f"Збережено підрозділ: {text}")
    
    # Запит департаменту
    markup = ReplyKeyboardMarkup(
        [[dept] for dept in DEPARTMENTS] + [["🔙 Назад"]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await update.message.reply_text(
        "*Оберіть ваш департамент:*",
        reply_markup=markup,
        parse_mode="Markdown"
    )
    return DEPARTMENT

async def department_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка вибраного департаменту"""
    text = update.message.text
    
    # 🔍 КРИТИЧНА ПЕРЕВІРКА: Якщо отримали кнопку з головного меню, завершуємо ConversationHandler
    if text and check_main_menu_button_and_exit(text, context, update):
        await update.message.reply_text(
            "🔄 *Повернення до головного меню*\n\n"
            "Для створення нової задачі натисніть *'🆕 Створити задачу'*.",
            reply_markup=main_menu_markup,
            parse_mode="Markdown"
        )
        return ConversationHandler.END
        
    if text == "🔙 Назад":
        # Повертаємо на головний екран і завершуємо ConversationHandler
        await update.message.reply_text(
            "🏠 *Головне меню*",
            reply_markup=main_menu_markup,
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    
    context.user_data["department"] = text
    
    # Переходимо до вибору сервісу
    await update.message.reply_text(
        "*Оберіть сервіс:*",
        reply_markup=service_selection_markup(SERVICES),
        parse_mode="Markdown"
    )
    return SERVICE


async def service_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Зберігає вибір сервісу та запитує опис проблеми"""
    text = update.message.text
    
    # 🔍 КРИТИЧНА ПЕРЕВІРКА: Якщо отримали кнопку з головного меню, завершуємо ConversationHandler
    if text and check_main_menu_button_and_exit(text, context, update):
        await update.message.reply_text(
            "🔄 *Повернення до головного меню*\n\n"
            "Для створення нової задачі натисніть *'🆕 Створити задачу'*.",
            reply_markup=main_menu_markup,
            parse_mode="Markdown"
        )
        return ConversationHandler.END
        
    if text == "🔙 Назад":
        # Повертаємо на головний екран і завершуємо ConversationHandler
        await update.message.reply_text(
            "🏠 *Головне меню*",
            reply_markup=main_menu_markup,
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    context.user_data["service"] = text
    await update.message.reply_text("*Опишіть проблему у кілька речень:*", reply_markup=ReplyKeyboardRemove(), parse_mode="Markdown")
    return DESCRIPTION


async def description_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Зберігає опис проблеми і показує підсумок"""
    # Перевіряємо текстові повідомлення на кнопки головного меню
    if update.message.text:
        text = update.message.text.strip()
        # 🔍 КРИТИЧНА ПЕРЕВІРКА: Якщо отримали кнопку з головного меню, завершуємо ConversationHandler
        if check_main_menu_button_and_exit(text, context, update):
            await update.message.reply_text(
                "🔄 *Повернення до головного меню*\n\n"
                "Для створення нової задачі натисніть *'🆕 Створити задачу'*.",
                reply_markup=main_menu_markup,
                parse_mode="Markdown"
            )
            return ConversationHandler.END
    
    # Обробляємо як текст, так і фото з підписом
    if update.message.photo:
        # Якщо користувач відправив фото
        description = update.message.caption or ""
        if not description.strip():
            await update.message.reply_text(
                "❌ *Помилка:* Будь ласка, додайте опис проблеми в підпис до фото.",
                parse_mode="Markdown"
            )
            return DESCRIPTION
        
        # Зберігаємо фото для подальшого прикріплення до задачі
        photo = update.message.photo[-1]  # Беремо найбільшу версію фото
        context.user_data["attached_photo"] = {
            "file_id": photo.file_id,
            "file_unique_id": photo.file_unique_id,
            "caption": description
        }
        context.user_data["description"] = description
        
        await update.message.reply_text(
            "📸 *Фото збережено!* Воно буде прикріплено до задачі після створення."
        )
    else:
        # Звичайний текстовий опис
        description = update.message.text
        if not description or not description.strip():
            await update.message.reply_text(
                "❌ *Помилка:* Опис проблеми не може бути пустим.",
                parse_mode="Markdown"
            )
            return DESCRIPTION
        context.user_data["description"] = description
    
    # 🚀 НОВА ЛОГІКА: Автоматичне створення задачі одразу після опису
    await update.message.reply_text(
        "📝 *Опис збережено! Створюємо задачу...*",
        parse_mode="Markdown"
    )
    
    # Створюємо задачу автоматично
    try:
        bot_vars = context.user_data.copy()
        
        # Формуємо опис для задачі
        task_description = (
            f"ПІБ: {bot_vars.get('full_name','')}\n"
            f"Підрозділ: {bot_vars.get('division','')}\n"
            f"Департамент: {bot_vars.get('department','')}\n"
            f"Сервіс: {bot_vars.get('service','')}\n"
            f"Опис: {bot_vars.get('description','')}"
        )
        
        # Додаємо поля проекта та типа задачі, якщо їх немає
        if "issuetype" not in bot_vars:
            bot_vars["issuetype"] = JIRA_ISSUE_TYPE
        
        if "project" not in bot_vars:
            bot_vars["project"] = JIRA_PROJECT_KEY
        
        # Додаємо summary та description
        bot_vars["summary"] = f"{bot_vars.get('service', 'Загальний')}: {bot_vars.get('description', '')[:50]}"
        bot_vars["description"] = task_description
        
        # 🚨 КРИТИЧНО: Додаємо telegram fields для JIRA (відновлено з confirm_callback)
        # telegram_id is required
        if not bot_vars.get("telegram_id"):
            bot_vars["telegram_id"] = str(update.effective_user.id)
        
        # telegram_username is optional, only add if user has it
        username = update.effective_user.username
        if username:  # only add if not None or empty
            bot_vars["telegram_username"] = username
        elif "telegram_username" in bot_vars:  # remove if exists but empty
            del bot_vars["telegram_username"]
        
        # Додаємо аккаунт репортера, якщо є
        if bot_vars.get("account_id") is None and JIRA_REPORTER_ACCOUNT_ID:
            bot_vars["account_id"] = JIRA_REPORTER_ACCOUNT_ID
        
        # Використовуємо функцію build_jira_payload замість ручного створення payload
        from src.services import build_jira_payload
        
        # Преобразуем значения полей, используя маппинги ID (відновлено з confirm_callback)
        from src.constants import DIVISION_ID_MAPPINGS, DEPARTMENT_ID_MAPPINGS, SERVICE_ID_MAPPINGS
        
        if "division" in bot_vars and bot_vars["division"] in DIVISION_ID_MAPPINGS:
            field_id = JIRA_FIELD_IDS["division"]
            bot_vars[field_id] = {"id": DIVISION_ID_MAPPINGS[bot_vars["division"]]["id"]}
            logger.info(f"Додано маппінг для division: {bot_vars['division']} -> {bot_vars[field_id]}")
        
        if "department" in bot_vars and bot_vars["department"] in DEPARTMENT_ID_MAPPINGS:
            field_id = JIRA_FIELD_IDS["department"]
            bot_vars[field_id] = {"id": DEPARTMENT_ID_MAPPINGS[bot_vars["department"]]["id"]}
            logger.info(f"Додано маппінг для department: {bot_vars['department']} -> {bot_vars[field_id]}")
        
        if "service" in bot_vars and bot_vars["service"] in SERVICE_ID_MAPPINGS:
            field_id = JIRA_FIELD_IDS["service"]
            bot_vars[field_id] = {"id": SERVICE_ID_MAPPINGS[bot_vars["service"]]["id"]}
            logger.info(f"Додано маппінг для service: {bot_vars['service']} -> {bot_vars[field_id]}")
        
        payload = build_jira_payload(bot_vars)
        
        # Логування для діагностики telegram_id
        logger.info(f"🔍 ДІАГНОСТИКА: Створення задачі з telegram_id={bot_vars.get('telegram_id')} та username={bot_vars.get('telegram_username')}")
        logger.info(f"🔍 Payload fields містить telegram_id: {'telegram_id' in str(payload)}")
        
        # Створюємо задачу в JIRA
        issue_key = await create_jira_issue(payload)
        
        # Встановлюємо активну задачу (відновлено з confirm_callback)
        context.user_data["active_task"] = issue_key
        
        # Прикріплюємо фото, якщо є
        if context.user_data.get("attached_photo"):
            try:
                photo_data = context.user_data["attached_photo"]
                # Get the file from Telegram
                file = await context.bot.get_file(photo_data["file_id"])
                # Generate filename
                filename = f"photo_{photo_data.get('file_unique_id', 'unknown')}.jpg"
                # Download file content as bytes
                file_bytes = await file.download_as_bytearray()
                # Attach to JIRA with proper parameters
                await attach_file_to_jira(issue_key, filename, bytes(file_bytes))
                
                await update.message.reply_text(
                    f"✅ *Задача створена:* `{issue_key}`\n"
                    f"📸 *Фото прикріплено успішно*\n\n"
                    f"_Тепер ви можете додати коментар або прикріпити інші файли._", 
                    reply_markup=issues_view_markup,
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Помилка прикріплення фото до задачі {issue_key}: {str(e)}")
                await update.message.reply_text(
                    f"✅ *Задача створена:* `{issue_key}`\n"
                    f"❌ *Помилка прикріплення фото:* _{str(e)}_\n\n"
                    f"_Ви можете спробувати прикріпити фото знову через коментарі._", 
                    reply_markup=issues_view_markup,
                    parse_mode="Markdown"
                )
        else:
            # Задача створена без фото
            await update.message.reply_text(
                f"✅ *Задача створена:* `{issue_key}`\n\n"
                f"_Тепер ви можете додати коментар або прикріпити файл._", 
                reply_markup=issues_view_markup,
                parse_mode="Markdown"
            )
        
        # Очищаємо дані conversation після успішного створення
        conversation_keys = ["full_name", "mobile_number", "division", "department", 
                           "service", "description", "attached_photo"]
        for key in conversation_keys:
            context.user_data.pop(key, None)
            
        return ConversationHandler.END
        
    except JiraApiError as e:
        error_message = str(e)
        # Обробляємо специфічні помилки JIRA
        if "400" in error_message:
            if "field" in error_message.lower() and "required" in error_message.lower():
                error_message = "Відсутні обов'язкові поля в запиті. Будь ласка, заповніть всі необхідні поля."
            elif "issuetype" in error_message.lower():
                error_message = "Вказано невірний тип задачі. Будь ласка, виберіть правильний тип."
            elif "project" in error_message.lower():
                error_message = "Вказано невірний проект. Будь ласка, виберіть правильний проект."
        
        logger.error(f"Помилка API Jira при створенні задачі: {str(e)}")
        await update.message.reply_text(
            f"❌ *Помилка створення задачі:* _{error_message}_", 
            reply_markup=issues_view_markup, 
            parse_mode="Markdown"
        )
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Невідома помилка при створенні задачі: {str(e)}")
        await update.message.reply_text(
            f"❌ *Помилка створення задачі.* _Будь ласка, спробуйте пізніше або зв'яжіться з адміністратором._", 
            reply_markup=issues_view_markup, 
            parse_mode="Markdown"
        )
        return ConversationHandler.END


async def confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка натискання Створити задачу або Назад"""
    query = update.callback_query
    await query.answer()
    if (query.data == "BACK_TO_SERVICE"):
        # Повернутися до вибору сервісу
        await query.message.reply_text(
            "*Оберіть сервіс:*",
            reply_markup=service_selection_markup(SERVICES),  # Используем SERVICES из constants.py
            parse_mode="Markdown"
        )
        return SERVICE
    
    # CONFIRM_CREATE
    bot_vars = context.user_data.copy()
    
    # Формуємо опис для задачі
    description = (
        f"ПІБ: {bot_vars.get('full_name','')}\n"
        f"Підрозділ: {bot_vars.get('division','')}\n"
        f"Департамент: {bot_vars.get('department','')}\n"
        f"Сервіс: {bot_vars.get('service','')}\n"
        f"Опис: {bot_vars.get('description','')}"
    )
    
    # Добавляем поле проекта и типа задачи, если они отсутствуют
    if "issuetype" not in bot_vars:
        bot_vars["issuetype"] = JIRA_ISSUE_TYPE  # Используем тип задачи из конфигурации
    
    # Изменяем ключ с project_key на project (в соответствии с fields_mapping.yaml)
    if "project" not in bot_vars:
        bot_vars["project"] = JIRA_PROJECT_KEY  # Используем код проекта из конфигурации
    
    # Добавляем summary и description
    bot_vars["summary"] = f"{bot_vars.get('service','')} - {bot_vars.get('description','')[:50]}"
    bot_vars["description"] = description

    # Add or update telegram fields for Jira
    # telegram_id is required
    if not bot_vars.get("telegram_id"):
        bot_vars["telegram_id"] = str(update.effective_user.id)
    
    # telegram_username is optional, only add if user has it
    username = update.effective_user.username
    if username:  # only add if not None or empty
        bot_vars["telegram_username"] = username
    elif "telegram_username" in bot_vars:  # remove if exists but empty
        del bot_vars["telegram_username"]
    
    # Добавляем аккаунт репортера, если есть
    if bot_vars.get("account_id") is None and JIRA_REPORTER_ACCOUNT_ID:
        bot_vars["account_id"] = JIRA_REPORTER_ACCOUNT_ID
    
    # Используем функцию build_jira_payload вместо ручного создания payload
    from services import build_jira_payload
    
    # Преобразуем значения полей, используя маппинги ID
    if "division" in bot_vars and bot_vars["division"] in DIVISION_ID_MAPPINGS:
        field_id = JIRA_FIELD_IDS["division"]
        bot_vars[field_id] = {"id": DIVISION_ID_MAPPINGS[bot_vars["division"]]["id"]}
        logger.info(f"Использую маппинг для division: {bot_vars['division']} -> {bot_vars[field_id]}")
    
    if "department" in bot_vars and bot_vars["department"] in DEPARTMENT_ID_MAPPINGS:
        field_id = JIRA_FIELD_IDS["department"]
        bot_vars[field_id] = {"id": DEPARTMENT_ID_MAPPINGS[bot_vars["department"]]["id"]}
        logger.info(f"Использую маппинг для department: {bot_vars['department']} -> {bot_vars[field_id]}")
    
    if "service" in bot_vars and bot_vars["service"] in SERVICE_ID_MAPPINGS:
        field_id = JIRA_FIELD_IDS["service"]
        bot_vars[field_id] = {"id": SERVICE_ID_MAPPINGS[bot_vars["service"]]["id"]}
        logger.info(f"Использую маппинг для service: {bot_vars['service']} -> {bot_vars[field_id]}")
    
    payload = build_jira_payload(bot_vars)
    
    try:
        logger.info(f"Отправка запроса на создание задачі з полями: {payload}")
        logger.info(f"Використовуємо тип задачі: {bot_vars.get('issuetype')}, проект: {bot_vars.get('project')}")
        
        # Переконаємось, що тип задачі та проект правильно вказані
        if 'fields' in payload and 'project' not in payload['fields']:
            payload['fields']['project'] = {'key': 'SD'} # Використовуємо дефолтний проект
            logger.info(f"Доданий дефолтний проект: SD")
            
        if 'fields' in payload and 'issuetype' not in payload['fields']:
            payload['fields']['issuetype'] = {'name': 'Telegram'} # Використовуємо дефолтний тип
            logger.info(f"Доданий дефолтний тип задачі: Telegram")
        
        # Додаємо перевірку на обов'язкові поля
        if 'fields' in payload and 'summary' not in payload['fields']:
            await query.message.reply_text("❌ *Помилка:* _відсутній заголовок задачі_", reply_markup=issues_view_markup, parse_mode="Markdown")
            return
        
        # Використовуємо правильно сформований payload
        issue_key = await create_jira_issue(payload)
        # Встановлюємо активну задачу
        context.user_data["active_task"] = issue_key
        
        # Перевіряємо, чи є прикріплене фото
        attached_photo = context.user_data.get("attached_photo")
        if attached_photo:
            try:
                # Завантажуємо і прикріплюємо фото до задачі
                from telegram import Bot
                
                bot = Bot(token=context.bot.token)
                file = await bot.get_file(attached_photo["file_id"])
                filename = f"photo_{attached_photo['file_unique_id']}.jpg"
                
                # Завантажуємо файл у пам'ять
                file_data = await file.download_as_bytearray()
                
                # Прикріплюємо до Jira (конвертуємо bytearray в bytes)
                await attach_file_to_jira(issue_key, filename, bytes(file_data))
                
                # Очищаємо дані про фото
                del context.user_data["attached_photo"]
                
                await query.message.reply_text(
                    f"✅ Задача створена: *{issue_key}*\n"
                    f"📸 Фото успішно прикріплено до задачі!\n"
                    f"_Тепер ви можете додати коментар або прикріпити інші файли._", 
                    reply_markup=issues_view_markup,
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Помилка прикріплення фото до задачі {issue_key}: {str(e)}")
                await query.message.reply_text(
                    f"✅ Задача створена: *{issue_key}*\n"
                    f"❌ Помилка прикріплення фото: _{str(e)}_\n"
                    f"_Ви можете спробувати прикріпити фото знову через коментарі._", 
                    reply_markup=issues_view_markup,
                    parse_mode="Markdown"
                )
        else:
            # Змінюємо клавіатуру на issues_view_markup для відображення кнопок оновлення статусу
            await query.message.reply_text(f"✅ Задача створена: *{issue_key}*\n_Тепер ви можете додати коментар або прикріпити файл._", 
                                        reply_markup=issues_view_markup,
                                        parse_mode="Markdown")
    except JiraApiError as e:
        error_message = str(e)
        # Извлекаем информативную часть сообщения об ошибке
        if "400" in error_message:
            if "field" in error_message.lower() and "required" in error_message.lower():
                error_message = "Відсутні обов'язкові поля в запиті. Будь ласка, заповніть всі необхідні поля."
            elif "issuetype" in error_message.lower():
                error_message = "Вказано невірний тип задачі. Будь ласка, виберіть правильний тип."
            elif "project" in error_message.lower():
                error_message = "Вказано невірний проект. Будь ласка, виберіть правильний проект."
            else:
                error_message = "Помилка у форматі запиту. Будь ласка, перевірте введені дані."
        elif "401" in error_message or "403" in error_message:
            error_message = "Проблема з авторизацією в Jira. Будь ласка, зв'яжіться з адміністратором."
        elif "timeout" in error_message.lower():
            error_message = "Перевищено час очікування відповіді від Jira. Спробуйте ще раз пізніше."
        
        logger.error(f"Помилка при створенні задачі: {str(e)}")
        await query.message.reply_text(f"❌ *Помилка створення задачі:* _{error_message}_", reply_markup=issues_view_markup, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Невідома помилка при створенні задачі: {str(e)}")
        await query.message.reply_text(f"❌ *Помилка створення задачі.* _Будь ласка, спробуйте пізніше або зв'яжіться з адміністратором._", reply_markup=issues_view_markup, parse_mode="Markdown")
    
    # Автоматичне збереження нового користувача в Google Sheets (якщо це новий користувач)
    profile = context.user_data.get("profile")
    if not profile or not profile.get("telegram_id"):
        # Це новий користувач - збережемо його в Google Sheets
        try:
            new_user_data = {
                "full_name": context.user_data.get("full_name", ""),
                "mobile_number": context.user_data.get("mobile_number", ""),
                "division": context.user_data.get("division", ""),
                "department": context.user_data.get("department", ""),
                "telegram_id": context.user_data.get("telegram_id", ""),
                "telegram_username": context.user_data.get("telegram_username", ""),
                "email": "",  # Поки що залишаємо порожнім
                "account_id": context.user_data.get("account_id", "")
            }
            
            if new_user_data["full_name"] and new_user_data["telegram_id"]:
                from src.google_sheets_service import add_new_user
                row_num = add_new_user(new_user_data)
                logger.info(f"Новий користувач {new_user_data['full_name']} автоматично додано в Google Sheets: рядок {row_num}")
                
                # Зберігаємо профіль користувача в контексті для майбутніх взаємодій
                context.user_data["profile"] = new_user_data
        except Exception as e:
            logger.error(f"Помилка автоматичного додавання нового користувача в Google Sheets: {e}")
    
    # Задачу створено успішно, виходимо з ConversationHandler
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скасувати ConversationHandler"""
    await update.message.reply_text("❌ *Скасовано.*", reply_markup=issues_view_markup, parse_mode="Markdown")
    return ConversationHandler.END


async def show_active_task_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показує детальну інформацію про активну задачу"""
    key = context.user_data.get("active_task")
    if not key:
        # Визначаємо, як відправити повідомлення
        if update.callback_query:
            await update.callback_query.message.reply_text("❗ *Немає активної задачі для перегляду.*", reply_markup=issues_view_markup, parse_mode="Markdown")
        else:
            await update.message.reply_text("❗ *Немає активної задачі для перегляду.*", reply_markup=issues_view_markup, parse_mode="Markdown")
        return False

    try:
        # Отримуємо повні деталі задачі з Jira
        issue = await get_full_issue_info(key)
        
        # Логуємо отримані дані для діагностики проблеми з департаментом
        logger.info(f"Отримані дані задачі {key} від Jira API: department={issue.get('department')}, division={issue.get('division')}, service={issue.get('service')}")
        
        # Используем модуль форматирования для единообразного отображения
        from fixed_issue_formatter import format_issue_info, format_issue_text
        
        # Получаем отформатированные данные
        formatted_issue = format_issue_info(issue)
        logger.info(f"Відформатовані дані задачі {key}: department={formatted_issue.get('department')}, division={formatted_issue.get('division')}, service={formatted_issue.get('service')}")
        
        # Формируем текст и добавляем защиту от разбивки на символы
        text = format_issue_text(formatted_issue)
        
        # Добавляем маркер невидимого пробела в начало текста, чтобы предотвратить разбиение на символы
        text = '\u200B' + text
        
        # Визначаємо, як відправити повідомлення
        if update.callback_query:
            await update.callback_query.message.reply_text(
                text,
                reply_markup=issues_view_markup,
                parse_mode=None  # Отключаем парсинг Markdown/HTML для предотвращения проблем с форматированием
            )
        else:
            await update.message.reply_text(
                text,
                reply_markup=issues_view_markup,
                parse_mode=None  # Отключаем парсинг Markdown/HTML для предотвращения проблем с форматированием
            )
        return True
    except Exception as e:
        logger.error(f"Помилка отримання деталей задачі {key}: {str(e)}")
        
        # Визначаємо, як відправити повідомлення про помилку
        if update.callback_query:
            await update.callback_query.message.reply_text(
                f"❌ Помилка отримання деталей задачі {key}: {str(e)}",
                reply_markup=issues_view_markup
            )
        else:
            await update.message.reply_text(
                f"❌ Помилка отримання деталей задачі {key}: {str(e)}",
                reply_markup=issues_view_markup
            )
        return False


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник для кнопки 'ℹ️ Допомога' - перенаправляє користувача до телеграм-каналу підтримки"""
    await update.message.reply_text(
        "Для отримання допомоги перейдіть до каналу підтримки: https://t.me/+zoabM0XuLeo2NzY6\n\n"
        "Там ви зможете поставити питання і отримати консультацію.",
        reply_markup=main_menu_markup
    )


def register_handlers(application):
    """Реєстрація всіх хендлерів у Application"""
    # ConversationHandler для створення задачі
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & filters.Regex("^🆕 Створити задачу$"), create_issue_start)],
        states={
            FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^🏠 Вийти на головну$"), full_name_handler),
                       MessageHandler(filters.Regex("^🏠 Вийти на головну$"), return_to_main_from_conversation)],
            MOBILE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^🏠 Вийти на головну$"), mobile_number_handler), 
                          MessageHandler(filters.CONTACT, contact_handler),
                          MessageHandler(filters.Regex("^🏠 Вийти на головну$"), return_to_main_from_conversation)],

            DIVISION: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^🏠 Вийти на головну$"), division_handler),
                      MessageHandler(filters.Regex("^🏠 Вийти на головну$"), return_to_main_from_conversation)],
            DEPARTMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^🏠 Вийти на головну$"), department_handler),
                        MessageHandler(filters.Regex("^🏠 Вийти на головну$"), return_to_main_from_conversation)],
            SERVICE: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^🏠 Вийти на головну$"), service_handler),
                     MessageHandler(filters.Regex("^🏠 Вийти на головну$"), return_to_main_from_conversation)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^🏠 Вийти на головну$"), description_handler),
                         MessageHandler(filters.PHOTO, description_handler),
                         MessageHandler(filters.Regex("^🏠 Вийти на головну$"), return_to_main_from_conversation)],
            CONFIRM: [CallbackQueryHandler(confirm_callback, pattern="^(CONFIRM_CREATE|BACK_TO_SERVICE)$")],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)],
        per_message=False,  # Возвращаем обратно для совместимости с MessageHandler
        name="create_issue_conversation"
    )

    # Важно: ConversationHandler должен быть перед общими обработчиками текста
    application.add_handler(conv_handler)
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Regex("🆕 Створити задачу"), create_task_button_handler))
    application.add_handler(MessageHandler(filters.Regex("🔄 Повторити /start"), restart_handler))
    application.add_handler(MessageHandler(filters.Regex("🔄 Повторна авторизація"), re_auth_handler))
    application.add_handler(MessageHandler(filters.Regex("👤 Мій профіль"), my_profile_handler))
    # Глобальний contact_handler для початкової авторизації з головного меню
    application.add_handler(MessageHandler(filters.CONTACT, global_contact_handler))
    application.add_handler(MessageHandler(filters.Regex("👤 Продовжити без авторизації"), continue_without_auth))
    application.add_handler(MessageHandler(filters.Regex("🧾 Мої задачі"), my_issues))
    application.add_handler(CallbackQueryHandler(issue_callback, pattern="^ISSUE_"))
    # Додаємо обробник для інлайн кнопки "Вийти на головне"
    application.add_handler(CallbackQueryHandler(back_to_main_callback, pattern="^BACK_TO_MAIN$"))
    application.add_handler(MessageHandler(filters.Regex("🏠 Вийти на головну"), return_to_main))
    # Обробник для оновлення статусів задач
    application.add_handler(MessageHandler(filters.Regex("🔄 Оновити статус задачі"), update_issues_status))
    application.add_handler(MessageHandler(filters.Regex("✅ Перевірити статус задачі"), check_status))
    # Обробник для кнопки коментування
    application.add_handler(MessageHandler(filters.Regex("💬 коментар до задачі"), comment_handler))
    application.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO | filters.VIDEO | filters.AUDIO, file_handler))
    # Обробник для кнопки допомоги
    application.add_handler(MessageHandler(filters.Regex("ℹ️ Допомога"), help_handler))

    # Обробник комментариев (МАЄ БУТИ ПЕРЕД global_registration_handler)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & ~filters.Regex("^(🆕|🧾|✅|🏠|🔄 Оновити статус задачі|🔄 Повторити /start|🔄 Повторна авторизація|👤|❌|ℹ️|💬 коментар до задачі)"), 
        comment_handler
    ))
    
    # Глобальний обробник реєстрації нових користувачів (ПІСЛЯ обробника коментарів)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & ~filters.Regex("^(🆕 Створити задачу|🧾|✅|🏠|🔄|👤|❌|ℹ️)"),
        global_registration_handler
    ))