# handlers.py

import logging
import re

from telegram import Update, ReplyKeyboardRemove, ReplyKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ConversationHandler,
    ApplicationHandlerStop,
)

from src.google_sheets_service import (
    find_user_by_phone,
    find_user_by_telegram_id,
    update_user_telegram,
)
from src.user_management_service import user_manager
from src.user_state_service import (
    save_registration_state,
    load_registration_state,
    complete_registration,
    BotState,
    get_user_bot_state,
    set_user_bot_state,
    complete_user_registration_and_set_state,
    set_user_current_task,
    clear_user_current_task,
    get_user_current_task,
)
from src.services import (
    create_jira_issue,
    find_open_issues,
    find_done_issues,
    add_comment_to_jira,
    add_comment_with_file_reference_to_jira,
    JiraApiError,
    attach_file_to_jira,
    get_issue_status,
    get_full_issue_info,
)
from src.constants import (
    DIVISIONS,
    DEPARTMENTS,
    SERVICES,
    DIVISION_ID_MAPPINGS,
    DEPARTMENT_ID_MAPPINGS,
    SERVICE_ID_MAPPINGS,
    JIRA_FIELD_IDS,
)
from src.keyboards import (
    main_menu_markup,
    contact_request_markup,
    service_selection_markup,
    issues_view_markup,
)
from config.config import JIRA_REPORTER_ACCOUNT_ID, JIRA_PROJECT_KEY, JIRA_ISSUE_TYPE

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
    # Нормалізуємо номер, прибираючи дозволені роздільники
    clean_phone = re.sub(r"[\s\-\(\)]", "", phone)

    # Перевіряємо чи введено взагалі щось схоже на номер
    if not clean_phone:
        return False, "Номер телефону не може бути пустим"

    # Перевіряємо чи є в тексті щось, крім цифр, пробілів, дефісів та +
    if re.search(r"[^\d\s\-\(\)\+]", phone):
        normalized_phone = clean_phone
        if normalized_phone.startswith("+380") and re.search(r"[A-Za-z]", normalized_phone[4:]):
            return False, "Після +380 мають йти тільки цифри"
        if normalized_phone.startswith("380") and re.search(r"[A-Za-z]", normalized_phone[3:]):
            return False, "Після 380 мають йти тільки цифри"
        return False, "Номер може містити тільки цифри, пробіли, дефіси та знак +"

    # Перевіряємо формат +380XXXXXXXXX (код країни +380 + 9 цифр)
    if clean_phone.startswith("+380"):
        if len(clean_phone) != 13:
            return (
                False,
                f"Номер має містити рівно 13 символів (+380 + 9 цифр), введено: {len(clean_phone)}",
            )

        digits_part = clean_phone[4:]  # Частина після +380
        if not digits_part.isdigit():
            return False, "Після +380 мають йти тільки цифри"

        if len(digits_part) != 9:
            return (
                False,
                f"Після +380 має бути рівно 9 цифр, введено: {len(digits_part)}",
            )

        return True, ""

    # Або формат без + (380XXXXXXXXX)
    elif clean_phone.startswith("380"):
        if len(clean_phone) != 12:
            return (
                False,
                f"Номер має містити рівно 12 цифр (380 + 9 цифр), введено: {len(clean_phone)}",
            )

        digits_part = clean_phone[3:]  # Частина після 380
        if not digits_part.isdigit():
            return False, "Після 380 мають йти тільки цифри"

        if len(digits_part) != 9:
            return (
                False,
                f"Після 380 має бути рівно 9 цифр, введено: {len(digits_part)}",
            )

        return True, ""
    else:
        # Якщо номер не починається з +380 або 380
        if clean_phone.startswith("+"):
            return False, "Український номер має починатися з +380"
        else:
            return False, "Український номер має починатися з +380 або 380"


# Глобальная переменная для отслеживания статуса активных задач
active_task_is_done = False

# Кнопки головного меню для перевірки у ConversationHandler
MAIN_MENU_BUTTONS = [
    "🆕 Створити задачу",
    "🧾 Мої задачі",
    "👤 Мій профіль",
    "🔄 Оновити статус задачі",
    "🔄 Повторити /start",
    "🔄 Повторна авторизація",
    "ℹ️ Допомога",
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
        logger.warning(
            f"Користувач {user_id} натиснув кнопку головного меню '{text}' в ConversationHandler - завершуємо conversation"  # noqa: E501
        )

        # Очищаємо дані конверсації
        conversation_keys = [
            "full_name",
            "mobile_number",
            "division",
            "department",
            "service",
            "description",
            "attached_photo",
        ]
        for key in conversation_keys:
            context.user_data.pop(key, None)

        return True

    return False


def check_required_objects(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    require_message: bool = True,
    require_callback: bool = False,
) -> bool:
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


# === НОВИЙ ДИСПЕТЧЕР НА ОСНОВІ СТАНІВ ===


async def main_message_dispatcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Головний диспетчер повідомлень на основі стану користувача.
    Визначає стан користувача та перенаправляє на відповідний обробник.
    """
    if not update.message or not update.message.from_user:
        return

    telegram_id = update.message.from_user.id
    user_state = get_user_bot_state(telegram_id)

    logger.info(
        f"🔄 ДИСПЕТЧЕР: користувач {telegram_id}, стан: {user_state}, повідомлення: '{update.message.text[:50] if update.message.text else 'Non-text'}'"  # noqa: E501
    )

    # 🔥 КРИТИЧНО: Перевіряємо чи користувач не в активному ConversationHandler
    if context.user_data and context.user_data.get("in_conversation"):
        logger.info(
            f"⚠️ Користувач {telegram_id} в активному Conversation (in_conversation=True) - пропускаємо диспетчер"
        )
        return  # Не обробляємо, передаємо ConversationHandler

    # Якщо є context.user_data з ключами conversation, пропускаємо обробку
    if context.user_data and any(
        key in context.user_data
        for key in ["full_name", "division", "department", "service", "description"]
    ):
        logger.info(
            f"⚠️ Користувач {telegram_id} в активному Conversation - пропускаємо диспетчер"
        )
        return  # Не обробляємо, передаємо ConversationHandler

    # 1. Стан реєстрації - перенаправляємо на обробники реєстрації
    if user_state == BotState.REGISTRATION:
        logger.info(
            f"🔐 Користувач {telegram_id} в стані реєстрації - пропускаємо далі"
        )
        # Тут викликається логіка реєстрації (залишається без змін)
        return

    # 2. Стан авторизований без задач - обробляємо команди створення задач
    elif user_state == BotState.AUTHORIZED_NO_TASKS:
        logger.info(f"✅ Користувач {telegram_id} авторизований без відкритих задач")

        # Перевіряємо чи це не кнопка меню
        message_text = update.message.text if update.message.text else ""
        logger.info(
            f"🔍 ПЕРЕВІРКА: текст='{message_text}', startswith емодзі: {message_text.startswith(('🧾', '🆕', 'ℹ️', '🔄', '👤', '🏠'))}"  # noqa: E501
        )

        if update.message.text and update.message.text.startswith(
            ("🧾", "🆕", "ℹ️", "🔄", "👤", "🏠")
        ):
            logger.info(
                f"📱 Користувач {telegram_id} натиснув кнопку: {update.message.text} - пропускаємо далі"
            )
            return  # Пропускаємо кнопки до інших обробників

        # Перевіряємо чи користувач не в процесі створення задачі через inline кнопки
        if context.user_data.get("awaiting_description"):
            logger.info(
                f"⏳ Користувач {telegram_id} очікує введення опису - пропускаємо автоматичне створення"
            )
            return  # Пропускаємо до conversation handler'а

        # Якщо це текстове повідомлення (не кнопка), то це створення нової задачі
        if update.message.text and not update.message.text.startswith("/"):
            logger.info(
                f"🆕 Автоматичне створення задачі для користувача {telegram_id} з тексту: '{update.message.text[:50]}...'"  # noqa: E501
            )

            # Встановлюємо текст як опис задачі
            context.user_data["issue_description"] = update.message.text

            # Викликаємо стандартний create_issue_start з пропуском збору опису
            context.user_data["skip_description"] = True
            await create_issue_start(update, context)
            raise ApplicationHandlerStop  # Зупиняємо подальшу обробку

    # 3. Стан авторизований з задачею - обробляємо коментарі до задачі
    elif user_state == BotState.AUTHORIZED_WITH_TASK:
        current_task = get_user_current_task(telegram_id)
        logger.info(f"📝 Користувач {telegram_id} має відкриту задачу {current_task}")

        # Перевіряємо чи це не кнопка меню
        if update.message.text and update.message.text.startswith(
            ("🧾", "🆕", "ℹ️", "🔄", "👤", "🏠")
        ):
            logger.info(
                f"📱 Користувач {telegram_id} натиснув кнопку: {update.message.text} - пропускаємо далі"
            )
            return  # Пропускаємо кнопки до інших обробників

        # ✅ ДОДАНО: Логування для діагностики медіа
        if update.message.photo:
            logger.info(f"📸 Отримано фото від користувача {telegram_id}")
        elif update.message.document:
            logger.info(f"📄 Отримано документ від користувача {telegram_id}")
        elif update.message.video:
            logger.info(f"🎥 Отримано відео від користувача {telegram_id}")
        elif update.message.audio:
            logger.info(f"🎵 Отримано аудіо від користувача {telegram_id}")

        # Всі повідомлення (текст, файли) - це коментарі до поточної задачі
        if (
            update.message.text
            or update.message.photo
            or update.message.document
            or update.message.video
            or update.message.audio
        ):  # ✅ Додано video та audio
            await handle_task_comment(update, context, current_task)
            raise ApplicationHandlerStop  # Зупиняємо подальшу обробку

    # Якщо не оброблено вище, пропускаємо далі до інших обробників
    logger.info("⏭️ Повідомлення не оброблено диспетчером, передаємо далі")


async def handle_inline_issue_description(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Обробляє введення опису задачі після вибору сервісу через inline кнопки"""
    if not update.message or not update.message.text:
        return

    # 🔥 КРИТИЧНО: Перевіряємо чи користувач не в активному ConversationHandler
    if context.user_data and context.user_data.get("in_conversation"):
        logger.info(
            "⚠️ Користувач в активному Conversation (in_conversation=True) - пропускаємо inline handler"
        )
        return  # Не обробляємо, передаємо ConversationHandler

    # Перевіряємо чи є будь-який ключ conversation в context
    if context.user_data:
        conversation_active = any(
            key in context.user_data
            for key in [
                "full_name",
                "division",
                "department",
                "service",
                "mobile_number",
                "awaiting_contact",
                "conversation_state",
            ]
        )
        if conversation_active:
            logger.info(
                "⚠️ Користувач в активному Conversation - пропускаємо inline handler"
            )
            return  # Не обробляємо, передаємо ConversationHandler

    # Перевіряємо чи користувач очікує введення опису
    if not context.user_data.get("awaiting_description"):
        return

    telegram_id = update.message.from_user.id
    description = update.message.text

    logger.info(
        f"📝 Отримано опис задачі від користувача {telegram_id}: '{description[:50]}...'"
    )

    # Зберігаємо опис
    context.user_data["description"] = description
    context.user_data["issue_description"] = description

    # Видаляємо флаг очікування
    context.user_data.pop("awaiting_description", None)

    # Тепер створюємо задачу автоматично
    await update.message.reply_text("📝 *Створюємо задачу...*", parse_mode="Markdown")

    try:
        # Копіюємо логіку створення задачі з service_selection_callback
        bot_vars = context.user_data.copy()

        # Формуємо опис для задачі
        task_description = (
            f"ПІБ: {bot_vars.get('full_name', '')}\n"
            f"Підрозділ: {bot_vars.get('division', '')}\n"
            f"Департамент: {bot_vars.get('department', '')}\n"
            f"Сервіс: {bot_vars.get('service', '')}\n"
            f"Опис: {bot_vars.get('description', '')}"
        )

        # Додаємо поля проекта та типа задачі
        if "issuetype" not in bot_vars:
            bot_vars["issuetype"] = JIRA_ISSUE_TYPE

        if "project" not in bot_vars:
            bot_vars["project"] = JIRA_PROJECT_KEY

        # Додаємо summary та description
        bot_vars["summary"] = (
            f"{bot_vars.get('service', 'Загальний')}: {bot_vars.get('description', '')[:50]}"
        )
        bot_vars["description"] = task_description

        # Додаємо telegram fields для JIRA
        if not bot_vars.get("telegram_id"):
            bot_vars["telegram_id"] = str(telegram_id)

        username = update.message.from_user.username
        if username:
            bot_vars["telegram_username"] = username
        elif "telegram_username" in bot_vars:
            del bot_vars["telegram_username"]

        # Додаємо аккаунт репортера
        if bot_vars.get("account_id") is None and JIRA_REPORTER_ACCOUNT_ID:
            bot_vars["account_id"] = JIRA_REPORTER_ACCOUNT_ID

        # Використовуємо функції з сервісів
        from src.services import build_jira_payload, create_jira_issue
        from src.constants import (
            DIVISION_ID_MAPPINGS,
            DEPARTMENT_ID_MAPPINGS,
            SERVICE_ID_MAPPINGS,
        )

        if "division" in bot_vars and bot_vars["division"] in DIVISION_ID_MAPPINGS:
            field_id = JIRA_FIELD_IDS["division"]
            bot_vars[field_id] = {
                "id": DIVISION_ID_MAPPINGS[bot_vars["division"]]["id"]
            }

        if (
            "department" in bot_vars
            and bot_vars["department"] in DEPARTMENT_ID_MAPPINGS
        ):
            field_id = JIRA_FIELD_IDS["department"]
            bot_vars[field_id] = {
                "id": DEPARTMENT_ID_MAPPINGS[bot_vars["department"]]["id"]
            }

        if "service" in bot_vars and bot_vars["service"] in SERVICE_ID_MAPPINGS:
            field_id = JIRA_FIELD_IDS["service"]
            bot_vars[field_id] = {"id": SERVICE_ID_MAPPINGS[bot_vars["service"]]["id"]}

        payload = build_jira_payload(bot_vars)

        # Створюємо задачу в JIRA
        issue_key = await create_jira_issue(payload)

        # Встановлюємо активну задачу
        context.user_data["active_task"] = issue_key

        # Оновлюємо стан користувача
        set_user_current_task(telegram_id, issue_key)
        logger.info(
            f"🔄 Стан користувача {telegram_id} змінено на AUTHORIZED_WITH_TASK з задачею {issue_key}"
        )

        # Очищаємо тимчасові дані
        context.user_data.clear()
        context.user_data["active_task"] = issue_key
        context.user_data["telegram_id"] = str(telegram_id)

        await update.message.reply_text(
            f"✅ *Задача створена!*\n\n"
            f"🎫 *Номер задачі:* `{issue_key}`\n"
            f"📝 *Опис:* {description[:100]}{'...' if len(description) > 100 else ''}\n\n"
            f"💬 _Тепер ви можете писати коментарі - вони автоматично додаватимуться до цієї задачі._",
            reply_markup=main_menu_markup,
            parse_mode="Markdown",
        )

    except Exception as e:
        logger.error(f"Помилка при створенні задачі через inline опис: {e}")
        await update.message.reply_text(
            "❌ *Помилка при створенні задачі*",
            reply_markup=main_menu_markup,
            parse_mode="Markdown",
        )

    # Завжди зупиняємо подальшу обробку після завершення
    raise ApplicationHandlerStop


async def handle_task_comment(
    update: Update, context: ContextTypes.DEFAULT_TYPE, task_key: str
):
    """Обробляє коментар до існуючої задачі"""
    telegram_id = update.message.from_user.id

    logger.info(
        f"💬 Додавання коментаря до задачі {task_key} від користувача {telegram_id}"
    )

    # Спочатку перевіряємо статус задачі
    try:
        status_info = await get_issue_status(task_key)
        status_category = status_info.get("category", "")
        status_name = status_info.get("name", "")

        logger.info(
            f"🔍 Статус задачі {task_key}: {status_name} (категорія: {status_category})"
        )

        # Якщо задача закрита (статус категорія "Done" або "Готово"), забороняємо додавання коментарів
        if status_category in ["Done", "Готово"]:
            logger.warning(
                f"🚫 Спроба додати коментар до закритої задачі {task_key} зі статусом {status_name}"
            )

            # Очищаємо поточну задачу користувача
            clear_user_current_task(telegram_id)

            # Оновлюємо стан користувача на AUTHORIZED_NO_TASKS
            set_user_bot_state(telegram_id, BotState.AUTHORIZED_NO_TASKS)

            # Екрануємо спеціальні символи для MarkdownV2
            task_key_escaped = task_key.replace("-", "\\-")
            status_name_escaped = status_name.replace("-", "\\-").replace(".", "\\.")

            await update.message.reply_text(
                f"❌ Задача *{task_key_escaped}* вже завершена \\(статус: _{status_name_escaped}_\\)\\.\n"
                f"Неможливо додавати коментарі до закритих задач\\.\n\n"
                f"📝 Для створення нової задачі просто опишіть проблему\\.",
                parse_mode="MarkdownV2",
            )
            return

    except Exception as e:
        logger.error(f"Помилка перевірки статусу задачі {task_key}: {e}")
        await update.message.reply_text("❌ Помилка перевірки статусу задачі")
        return

    # Отримуємо дані користувача
    try:
        from src.user_state_service import load_user_profile

        user_profile = load_user_profile(telegram_id)
        if not user_profile:
            await update.message.reply_text(
                "❌ Помилка: профіль користувача не знайдено"
            )
            return

        author_name = user_profile.get("full_name", "Невідомий користувач")

        # Обробляємо різні типи повідомлень
        if update.message.photo:
            # Фото з текстом або без
            caption = update.message.caption or ""
            logger.info(f"📸 Обробка фото з підписом: '{caption}'")
            await handle_file_for_task(update, context, task_key, author_name)

        elif update.message.document:
            # Документ з текстом або без
            caption = update.message.caption or ""
            logger.info(f"📄 Обробка документу з підписом: '{caption}'")
            await handle_file_for_task(update, context, task_key, author_name)

        elif update.message.video:
            # Відео з текстом або без
            caption = update.message.caption or ""
            logger.info(f"🎥 Обробка відео з підписом: '{caption}'")
            await handle_file_for_task(update, context, task_key, author_name)

        elif update.message.audio:
            # Аудіо з текстом або без
            caption = update.message.caption or ""
            logger.info(f"🎵 Обробка аудіо з підписом: '{caption}'")
            await handle_file_for_task(update, context, task_key, author_name)

        elif update.message.text:
            # Текстовий коментар
            logger.info(
                f"💬 Обробка текстового коментаря: '{update.message.text[:50]}...'"
            )
            await text_comment_handler(update, context, task_key, author_name)

        else:
            logger.warning(
                f"❌ Непідтримуваний тип повідомлення від користувача {telegram_id}"
            )
            await update.message.reply_text("❌ Непідтримуваний тип повідомлення")

    except Exception as e:
        logger.error(f"Помилка обробки коментаря до {task_key}: {e}")
        await update.message.reply_text("❌ Помилка додавання коментаря")


async def handle_file_for_task(
    update: Update, context: ContextTypes.DEFAULT_TYPE, task_key: str, author_name: str
):
    """Обробляє файл для конкретної задачі"""
    try:
        # Встановлюємо задачу як активну для існуючого file_handler
        context.user_data["active_task"] = task_key

        # Викликаємо існуючий file_handler
        await file_handler(update, context)

    except Exception as e:
        logger.error(f"Помилка обробки файлу для задачі {task_key}: {e}")
        await update.message.reply_text("❌ Помилка обробки файлу")


async def text_comment_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE, task_key: str, author_name: str
):
    """Обробляє текстовий коментар до задачі"""
    text = update.message.text

    if not text:
        await update.message.reply_text("❌ Порожній коментар")
        return

    try:
        # Додаємо коментар до Jira
        await add_comment_to_jira(task_key, text, author_name)
        # Підтвердження користувачу (webhook не спрацює для коментарів від бота)
        await update.message.reply_text(f"✅ Коментар додано до задачі {task_key}")

    except Exception as e:
        logger.error(f"Помилка додавання текстового коментаря до {task_key}: {e}")
        await update.message.reply_text("❌ Помилка додавання коментаря")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обробник /start.
    Перевіряє авторизацію за Telegram ID та запитує контакт якщо потрібно.
    """
    # Type guards for required objects
    if not check_required_objects(
        update, context, require_message=False
    ):  # callback_query теж підтримується
        return

    # Універсальна функція для роботи з message і callback_query
    async def send_message(text, reply_markup=None, parse_mode=None):
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(
                text, reply_markup=reply_markup, parse_mode=parse_mode
            )
        else:
            await update.message.reply_text(
                text, reply_markup=reply_markup, parse_mode=parse_mode
            )

    user_id = str(update.effective_user.id)
    context.user_data["telegram_id"] = user_id
    tg_username = update.effective_user.username or ""

    # Очищаємо попередні дані тільки при прямому введенні команди /start
    # (не при виклику через restart_handler або callback)
    message_text = None
    if update.message and update.message.text:
        message_text = update.message.text
    elif update.callback_query and update.callback_query.data:
        message_text = update.callback_query.data

    if (
        message_text
        and (message_text == "/start" or message_text == "RESTART")
        and not context.user_data.get("profile")
    ):
        context.user_data.clear()
        context.user_data["telegram_id"] = user_id

    # Використовуємо гібридний сервіс для пошуку користувача
    logger.info(f"Комплексний пошук користувача за Telegram ID: {user_id}")
    user_data, source = await user_manager.find_user_comprehensive(int(user_id))

    if user_data:
        # Користувача знайдено
        logger.info(
            f"Користувача знайдено через: {source} - {user_data.get('full_name')}"
        )

        # Оновлюємо telegram_username, якщо змінився і source Google
        if (
            tg_username
            and tg_username != user_data.get("telegram_username", "")
            and source == "google"
        ):
            try:
                # Знаходимо рядок для оновлення
                res = find_user_by_telegram_id(user_id)
                if res:
                    _, row = res
                    update_user_telegram(row, user_id, tg_username)
                    user_data["telegram_username"] = tg_username
            except Exception as e:
                logger.warning(f"Не вдалось оновити username в Google Sheets: {e}")

        # Зберігаємо профіль
        context.user_data["profile"] = user_data

        # Показуємо детальне вітання з інформацією про джерело даних
        source_text = {
            "google": "🔄 *Дані отримано з Google Sheets*",
            "cache": "💾 *Дані отримано з локального кешу*",
        }.get(source, "")

        # Перевіряємо чи є відкрита задача
        current_task = get_user_current_task(int(user_id))
        task_info = ""
        if current_task:
            task_info = f"\n\n📋 *У вас є відкрита задача:* `{current_task}`\n💬 _Спочатку дочекайтесь її вирішення або додайте коментар до існуючої._"  # noqa: E501

        user_info = (
            f"👋 *Вітаємо, {user_data['full_name']}!*\n\n"
            f"👤 **ПІБ:** {user_data['full_name']}\n"
            f"📱 **Телефон:** {user_data.get('mobile_number', 'Не вказано')}\n"
            f"📍 **Підрозділ:** {user_data.get('division', 'Не вказано')}\n"
            f"🏢 **Департамент:** {user_data.get('department', 'Не вказано')}\n\n"
            f"{source_text}{task_info}\n\n"
            f"🎯 *Тепер ви можете користуватися всіма функціями бота.*"
        )

        await send_message(
            user_info, reply_markup=main_menu_markup, parse_mode="Markdown"
        )
    else:
        # Користувача не знайдено, запитуємо номер телефону для авторизації
        logger.info("Користувача не знайдено за Telegram ID, запитуємо номер телефону")
        await send_message(
            "👋 *Вітаємо в боті техпідтримки!*\n\n"
            "📱 *Натисніть кнопку щоб поділитися номером телефону:*",
            reply_markup=contact_request_markup,
            parse_mode="Markdown",
        )
        # Встановлюємо дані для нового користувача
        context.user_data["new_user"] = {
            "telegram_id": user_id,
            "telegram_username": tg_username,
        }


async def global_contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глобальний обробник контакту для початкової авторизації з головного меню"""
    # Type guards for required objects
    if (
        not update.message
        or not update.message.contact
        or not update.effective_user
        or not context.user_data
    ):
        logger.error("Missing required objects in global contact handler")
        return

    contact = update.message.contact
    phone = contact.phone_number
    telegram_id = int(update.effective_user.id)
    tg_username = update.effective_user.username or ""

    logger.info(f"Глобальна авторизація: отримано номер телефону {phone}")

    # Використовуємо гібридний сервіс для авторизації
    user_data, status = await user_manager.authorize_user(telegram_id, phone)

    if status == "authorized":
        # Користувача успішно авторизовано
        # Оновлюємо username в записі
        user_data["telegram_username"] = tg_username
        context.user_data["profile"] = user_data

        # Показуємо успішну авторизацію з повною інформацією про користувача
        cache_info = user_manager.get_user_cache_info(telegram_id)
        sync_status = (
            "🔄 *Синхронізовано з Google Sheets*"
            if cache_info.get("sync_status")
            else "💾 *Збережено в локальному кеші*"
        )

        user_info = (
            f"✅ *Ви успішно авторизовані!*\n\n"
            f"👤 **ПІБ:** {user_data['full_name']}\n"
            f"📱 **Телефон:** {phone}\n"
            f"📍 **Підрозділ:** {user_data.get('division', 'Не вказано')}\n"
            f"🏢 **Департамент:** {user_data.get('department', 'Не вказано')}\n\n"
            f"{sync_status}\n\n"
            f"🎯 *Тепер ви можете користуватися всіма функціями бота.*"
        )

        await update.message.reply_text(
            user_info, reply_markup=main_menu_markup, parse_mode="Markdown"
        )
        logger.info(f"Успішна глобальна авторизація для {user_data['full_name']}")

    elif status == "need_registration":
        # Номер не знайдено в базі - переходимо до реєстрації
        await update.message.reply_text(
            "⚠️ *Номер не знайдено в базі.*\n\n"
            "🆕 *Розпочинаємо процес реєстрації...*\n\n"
            "👤 *Для реєстрації введіть ваше повне ім'я (ПІБ):*",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown",
        )

        # Зберігаємо номер телефону для подальшого використання
        context.user_data["registration"] = {
            "phone": phone,
            "telegram_id": str(update.effective_user.id),
            "telegram_username": update.effective_user.username or "",
        }
        context.user_data["registration_step"] = "name"

        # Зберігаємо стан реєстрації у файл
        save_registration_state(telegram_id, context.user_data["registration"], "name")

        logger.info(f"Почато розширену реєстрацію нового користувача з номером {phone}")

    else:  # status == 'error'
        # Помилка доступу до баз даних
        await update.message.reply_text(
            "❌ *Помилка авторизації.*\n\n"
            "Зараз виникли технічні проблеми з доступом до бази даних. "
            "Спробуйте пізніше або зверніться до адміністратора.\n\n"
            "💾 *Ваші дані можуть бути збережені в локальному кеші для майбутнього використання.*",
            reply_markup=main_menu_markup,
            parse_mode="Markdown",
        )


async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка отриманого контакту для авторизації всередині ConversationHandler"""
    # Type guards for required objects
    if (
        not update.message
        or not update.message.contact
        or not update.effective_user
        or not context.user_data
    ):
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
            parse_mode="Markdown",
        )

        # Перевіряємо, чи перебуваємо ми в процесі створення заявки
        if context.user_data.get("full_name"):
            # Ми в процесі створення заявки, переходимо до наступного кроку
            markup = ReplyKeyboardMarkup(
                [[div] for div in DIVISIONS] + [["🔙 Назад"]],
                resize_keyboard=True,
                one_time_keyboard=True,
            )
            await update.message.reply_text(
                "*Оберіть ваш підрозділ:*", reply_markup=markup, parse_mode="Markdown"
            )
            return DIVISION
    else:
        # Не знайдено в базі - направляємо на розширену реєстрацію поза ConversationHandler
        await update.message.reply_text(
            "⚠️ *Номер не знайдено в базі.*\n\n"
            "Для реєстрації та створення задачі введіть ваше повне ім'я (ПІБ):",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown",
        )

        # Зберігаємо номер телефону для розширеної реєстрації
        context.user_data["registration"] = {
            "phone": phone,
            "telegram_id": str(update.effective_user.id),
            "telegram_username": update.effective_user.username or "",
        }
        context.user_data["registration_step"] = "name"

        # Зберігаємо стан реєстрації у файл
        telegram_id = int(update.effective_user.id)
        save_registration_state(telegram_id, context.user_data["registration"], "name")

        # ЗАВЕРШУЄМО ConversationHandler і переходимо до розширеної реєстрації
        logger.info(
            f"ConversationHandler: починаємо розширену реєстрацію для номера {phone}"
        )
        return ConversationHandler.END


async def global_registration_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
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
        if (
            saved_state
            and saved_state.get("state", {}).get("type") != "registration_completed"
        ):
            context.user_data["registration"] = saved_state["state"]["registration"]
            context.user_data["registration_step"] = saved_state["state"][
                "registration_step"
            ]
            registration_step = saved_state["state"]["registration_step"]
            logger.info(
                f"Відновлено стан реєстрації з файлу для користувача {telegram_id}: крок '{registration_step}'"
            )

            # Повідомляємо користувача про відновлення
            await update.message.reply_text(
                "🔄 *Відновлено процес реєстрації.*\n\n"
                "Продовжимо з того місця, де ви зупинилися...",
                parse_mode="Markdown",
            )
        elif (
            saved_state
            and saved_state.get("state", {}).get("type") == "registration_completed"
        ):
            # Реєстрацію завершено, очищаємо файл і пропускаємо
            logger.info("Реєстрацію користувача вже завершено, очищаємо стан")
            complete_registration(telegram_id)
            raise ApplicationHandlerStop()
        else:
            # Перевіряємо чи є файл стану - якщо немає, то користувач не в процесі реєстрації
            logger.info(
                f"Не в режимі реєстрації, завершуємо global_registration_handler для повідомлення: '{update.message.text}'"  # noqa: E501
            )
            # Просто повертаємось, щоб дозволити іншим handler'ам обробити повідомлення
            return

    if registration_step == "name":
        # Збираємо ПІБ з покращеною валідацією
        full_name = update.message.text.strip()

        # Покращена валідація ПІБ
        if not full_name:
            await update.message.reply_text(
                "❌ *ПІБ не може бути пустим.*\n\n"
                "Будь ласка, введіть ваше повне ім'я (ПІБ):",
                parse_mode="Markdown",
            )
            return

        if len(full_name) < 3:
            await update.message.reply_text(
                "❌ *ПІБ занадто короткий.* _(мінімум 3 символи)_\n\n"
                "Будь ласка, введіть ваше повне ім'я (ПІБ):",
                parse_mode="Markdown",
            )
            return

        # Перевіряємо чи є принаймні два слова (ім'я та прізвище)
        name_parts = full_name.split()
        if len(name_parts) < 2:
            await update.message.reply_text(
                "❌ *Будь ласка, введіть повне ім'я* _(принаймні ім'я та прізвище)_\n\n"
                "Приклад: Іван Петренко або Іван Іванович Петренко",
                parse_mode="Markdown",
            )
            return

        # Перевіряємо чи немає цифр у ПІБ
        if any(char.isdigit() for char in full_name):
            await update.message.reply_text(
                "❌ *ПІБ не може містити цифри.*\n\n"
                "Будь ласка, введіть ваше повне ім'я (ПІБ):",
                parse_mode="Markdown",
            )
            return

        # Зберігаємо ПІБ і переходимо до підрозділу
        context.user_data["registration"]["full_name"] = full_name
        context.user_data["registration_step"] = "division"

        # Зберігаємо стан у файл
        save_registration_state(
            telegram_id, context.user_data["registration"], "division"
        )

        # Запитуємо підрозділ
        markup = ReplyKeyboardMarkup(
            [[div] for div in DIVISIONS], resize_keyboard=True, one_time_keyboard=True
        )
        await update.message.reply_text(
            f"✅ *Дякуємо, {full_name}!*\n\n" "📍 *Оберіть ваш підрозділ зі списку:*",
            reply_markup=markup,
            parse_mode="Markdown",
        )

    elif registration_step == "division":
        # Збираємо підрозділ з покращеною валідацією
        division = update.message.text.strip()

        # Перевіряємо чи підрозділ у списку дозволених
        if division not in DIVISIONS:
            valid_divisions = "', '".join(
                DIVISIONS[:5]
            )  # Показуємо перші 5 для прикладу
            await update.message.reply_text(
                f"❌ *Підрозділ '{division}' не знайдено в списку.*\n\n"
                f"📍 *Доступні підрозділи:*\n'{valid_divisions}'...\n\n"
                "*Будь ласка, оберіть підрозділ зі списку кнопок нижче:*",
                parse_mode="Markdown",
            )
            return

        # Зберігаємо підрозділ і переходимо до департаменту
        context.user_data["registration"]["division"] = division
        context.user_data["registration_step"] = "department"

        # Зберігаємо стан у файл
        save_registration_state(
            telegram_id, context.user_data["registration"], "department"
        )

        # Запитуємо департамент
        markup = ReplyKeyboardMarkup(
            [[dept] for dept in DEPARTMENTS],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        await update.message.reply_text(
            f"📍 *Підрозділ: {division}*\n\n"
            "🏢 *Тепер оберіть ваш департамент зі списку:*",
            reply_markup=markup,
            parse_mode="Markdown",
        )

    elif registration_step == "department":
        # Збираємо департамент з покращеною валідацією
        department = update.message.text.strip()

        # Перевіряємо чи департамент у списку дозволених
        if department not in DEPARTMENTS:
            valid_departments = "', '".join(
                DEPARTMENTS[:5]
            )  # Показуємо перші 5 для прикладу
            await update.message.reply_text(
                f"❌ *Департамент '{department}' не знайдено в списку.*\n\n"
                f"🏢 *Доступні департаменти:*\n'{valid_departments}'...\n\n"
                "*Будь ласка, оберіть департамент зі списку кнопок нижче:*",
                parse_mode="Markdown",
            )
            return

        # Зберігаємо департамент
        context.user_data["registration"]["department"] = department

        # Переходимо до підтвердження
        context.user_data["registration_step"] = "confirm"

        # Зберігаємо стан у файл
        save_registration_state(
            telegram_id, context.user_data["registration"], "confirm"
        )

        # Показуємо підтвердження з усіма даними
        reg_data = context.user_data["registration"]
        confirmation_text = (
            "✅ *Перевірте та підтвердіть ваші дані:*\n\n"
            f"👤 **ПІБ:** {reg_data['full_name']}\n"
            f"📱 **Телефон:** {reg_data['phone']}\n"
            f"📍 **Підрозділ:** {reg_data['division']}\n"
            f"🏢 **Департамент:** {reg_data['department']}\n\n"
            "*Все правильно? Оберіть дію:*"
        )

        # Кнопки підтвердження з чіткими варіантами
        markup = ReplyKeyboardMarkup(
            [["✅ Підтвердити реєстрацію"], ["🔄 Почати заново"]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )

        logger.info(
            f"Показуємо підтвердження для користувача {telegram_id} з даними: {reg_data}"
        )
        await update.message.reply_text(
            confirmation_text, reply_markup=markup, parse_mode="Markdown"
        )

    elif registration_step == "confirm":
        # Обробляємо підтвердження
        confirmation = update.message.text.strip()

        logger.info(
            f"Отримано підтвердження: '{confirmation}' від користувача {telegram_id}"
        )

        # Покращена логіка розпізнавання підтвердження
        confirm_variations = [
            "✅ підтвердити реєстрацію",
            "підтвердити",
            "confirm",
            "так",
            "yes",
            "✅",
            "ok",
        ]
        restart_variations = [
            "🔄 почати заново",
            "почати заново",
            "restart",
            "заново",
            "спочатку",
        ]

        confirmation_lower = confirmation.lower()
        is_confirm = any(
            var.lower() in confirmation_lower for var in confirm_variations
        )
        is_restart = any(
            var.lower() in confirmation_lower for var in restart_variations
        )

        if is_restart:
            # Перезапускаємо реєстрацію з початку
            context.user_data["registration"] = {
                "telegram_id": str(update.effective_user.id),
                "telegram_username": update.effective_user.username or "",
            }
            context.user_data["registration_step"] = "name"

            # Зберігаємо початковий стан
            save_registration_state(
                telegram_id, context.user_data["registration"], "name"
            )

            await update.message.reply_text(
                "🔄 *Почнемо реєстрацію заново.*\n\n"
                "👤 *Введіть ваше повне ім'я (ПІБ):*",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode="Markdown",
            )
            return

        elif is_confirm:  # Якщо підтвердження
            # Перевіряємо чи всі дані заповнено
            reg_data = context.user_data.get("registration", {})
            required_fields = ["full_name", "phone", "division", "department"]
            missing_fields = [
                field for field in required_fields if not reg_data.get(field)
            ]

            if missing_fields:
                logger.error(
                    f"Відсутні обов'язкові поля для реєстрації: {missing_fields}"
                )
                await update.message.reply_text(
                    f"❌ *Помилка: не всі дані заповнено.*\n\n"
                    f"Відсутні поля: {', '.join(missing_fields)}\n\n"
                    "Почніть реєстрацію заново командою /start",
                    reply_markup=main_menu_markup,
                    parse_mode="Markdown",
                )
                # Очищаємо неповні дані
                context.user_data.pop("registration", None)
                context.user_data.pop("registration_step", None)
                complete_registration(telegram_id)
                return

            # Зберігаємо користувача через гібридний сервіс
            try:
                # Підготовуємо дані для Google Sheets
                new_user_data = {
                    "telegram_id": reg_data["telegram_id"],
                    "telegram_username": reg_data.get("telegram_username", ""),
                    "mobile_number": reg_data["phone"],
                    "full_name": reg_data["full_name"],
                    "division": reg_data["division"],
                    "department": reg_data["department"],
                }

                success, message, row_num = await user_manager.register_new_user(
                    new_user_data
                )

                if success:
                    # Зберігаємо профіль користувача в context
                    context.user_data["profile"] = new_user_data

                    # Очищаємо дані реєстрації
                    context.user_data.pop("registration", None)
                    context.user_data.pop("registration_step", None)

                    # Позначаємо реєстрацію як завершену та встановлюємо стан AUTHORIZED_NO_TASKS
                    complete_user_registration_and_set_state(telegram_id)

                    # Показуємо успішне завершення реєстрації з повною інформацією
                    success_message = (
                        f"🎉 *Реєстрацію завершено успішно!*\n\n"
                        f"👤 **ПІБ:** {reg_data['full_name']}\n"
                        f"📱 **Телефон:** {reg_data['phone']}\n"
                        f"📍 **Підрозділ:** {reg_data['division']}\n"
                        f"🏢 **Департамент:** {reg_data['department']}\n\n"
                        f"✅ *{message}*\n\n"
                        f"Тепер ви можете створювати задачі та користуватися всіма функціями бота."
                    )

                    await update.message.reply_text(
                        success_message,
                        reply_markup=main_menu_markup,
                        parse_mode="Markdown",
                    )

                    logger.info(
                        f"Нового користувача {reg_data['full_name']} успішно зареєстровано: {message}"
                    )
                else:
                    # Помилка реєстрації
                    await update.message.reply_text(
                        f"❌ *Помилка збереження даних.*\n\n"
                        f"Деталі: {message}\n\n"
                        "Спробуйте пізніше або зверніться до адміністратора.",
                        reply_markup=main_menu_markup,
                        parse_mode="Markdown",
                    )
            except Exception as e:
                logger.error(f"Критична помилка реєстрації: {e}")
                await update.message.reply_text(
                    f"❌ *Критична помилка реєстрації.*\n\n"
                    f"Деталі: {str(e)}\n\n"
                    "Спробуйте пізніше або зверніться до адміністратора.",
                    reply_markup=main_menu_markup,
                    parse_mode="Markdown",
                )
        else:
            # Невизначений ввід - показуємо доступні опції та повторюємо кнопки
            await update.message.reply_text(
                "❓ *Не зрозуміло ваш вибір.*\n\n" "Будь ласка, оберіть одну з опцій:",
                parse_mode="Markdown",
            )

            # Повторюємо кнопки підтвердження
            markup = ReplyKeyboardMarkup(
                [["✅ Підтвердити реєстрацію"], ["🔄 Почати заново"]],
                resize_keyboard=True,
                one_time_keyboard=True,
            )

            await update.message.reply_text(
                "Доступні варіанти:\n"
                "• '✅ Підтвердити реєстрацію' - завершити реєстрацію\n"
                "• '🔄 Почати заново' - розпочати реєстрацію спочатку",
                reply_markup=markup,
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
            parse_mode="Markdown",
        )
        return

    # Формуємо детальну інформацію про користувача
    user_info = "👤 *Ваш профіль:*\n\n"
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
        user_info, reply_markup=main_menu_markup, parse_mode="Markdown"
    )


async def re_auth_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник кнопки 'Повторна авторизація'"""
    # Type guards for required objects
    if not check_required_objects(update, context, require_message=True):
        return

    # Очищаємо профіль і дані користувача для повторної авторизації
    context.user_data.clear()
    user_id = str(update.effective_user.id)
    context.user_data["telegram_id"] = user_id

    await update.message.reply_text(
        "🔄 *Повторна авторизація*\n\n"
        "Для повторної авторизації надішліть ваш номер телефону:",
        reply_markup=contact_request_markup,
        parse_mode="Markdown",
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


async def my_issues(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показати список моїх відкритих задач у текстовому форматі"""
    profile = context.user_data.get("profile")
    user_id = str(update.effective_user.id)
    username = update.effective_user.username or "немає"

    # Універсальна функція для роботи з message і callback_query
    async def send_message(text, reply_markup=None, parse_mode=None):
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(
                text, reply_markup=reply_markup, parse_mode=parse_mode
            )
        else:
            await update.message.reply_text(
                text, reply_markup=reply_markup, parse_mode=parse_mode
            )

    # Розширене логування
    logger.info(f"my_issues: користувач ID={user_id}, username=@{username}")

    # Отримуємо telegram_id користувача з різних джерел
    telegram_id = None

    # 1. Спочатку спробуємо взяти з профілю
    if profile and profile.get("telegram_id"):
        telegram_id = (
            str(profile.get("telegram_id")).strip().replace("'", "")
        )  # Нормалізуємо ID
        logger.info(f"my_issues: взято ID з профілю: {telegram_id}")
    # 2. Інакше використовуємо ID поточного користувача
    else:
        telegram_id = user_id.strip().replace("'", "")  # Нормалізуємо ID
        logger.info(
            f"my_issues: використовуємо ID з поточного повідомлення: {telegram_id}"
        )

    # Показуємо нову клавіатуру для режиму перегляду задач
    await send_message(
        "_Завантажую список ваших задач..._",
        reply_markup=issues_view_markup,
        parse_mode="Markdown",
    )

    # Отримуємо список задач
    try:
        # Використовуємо фактичний telegram_id для пошуку
        issues = await find_open_issues(telegram_id)
        logger.info(f"my_issues: знайдено {len(issues)} задач для ID {telegram_id}")

        for issue in issues:
            logger.info(
                f"my_issues: задача {issue['key']} зі статусом {issue['status']}"
            )
    except Exception as e:
        logger.error(f"my_issues: помилка при пошуку задач для {telegram_id}: {str(e)}")
        issues = []
    if not issues:
        await send_message(
            "*У вас немає відкритих задач.* _Ви можете створити нову задачу, натиснувши кнопку '🆕 Створити задачу'._",
            reply_markup=main_menu_markup,
            parse_mode="Markdown",
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
        active_mark = (
            "➡️ " if issue["key"] == context.user_data.get("active_task") else ""
        )
        text_list.append(f"{active_mark}*`{issue['key']}`* — _{issue['status']}_")

    text_list.append(
        "\n_Щоб додати коментар до активної задачі, просто напишіть текст._"
    )

    # Виводимо список з форматуванням Markdown
    await update.message.reply_text(
        "\n".join(text_list), reply_markup=issues_view_markup, parse_mode="Markdown"
    )

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
        logger.info(
            f"update_issues_status: використовуємо ID з поточного повідомлення: {tg_id}"
        )

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
            active_task_is_done = any(
                issue["key"] == active_task for issue in done_issues
            )
            if active_task_is_done:
                # Виводимо спеціальне повідомлення для виконаної задачі
                _ = next(
                    (issue for issue in done_issues if issue["key"] == active_task),
                    None,
                )

                # Очищаємо поточну задачу користувача та оновлюємо стан
                clear_user_current_task(int(tg_id))
                set_user_bot_state(int(tg_id), BotState.AUTHORIZED_NO_TASKS)

                # Надсилаємо два повідомлення для гарантованої зміни клавіатури
                await update.message.reply_text(
                    f"*Статуси оновлено. Ваша задача:*\n➡️ *`{active_task}`* — *Виконана*.\n\n"
                    f"*Можете створити нову задачу, натиснувши відповідну кнопку в меню:*",
                    parse_mode="Markdown",
                )

                # Надсилаємо додаткове повідомлення з клавіатурою головного меню
                await update.message.reply_text(
                    "🏠 *Головне меню*",
                    reply_markup=main_menu_markup,
                    parse_mode="Markdown",
                )

                # Очищаємо активну задачу
                context.user_data.pop("active_task", None)
                return

        # Якщо задач немає в API, але є активна задача в контексті (тільки що створена)
        if not open_issues and active_task and not active_task_is_done:
            await update.message.reply_text(
                f"Задача `{active_task}` ще не відображається в системі. Спробуйте оновити статус через кілька хвилин.",
                reply_markup=issues_view_markup,
                parse_mode="Markdown",
            )
            return
        # Якщо задач немає взагалі
        elif not open_issues:
            await update.message.reply_text(
                "*У вас немає відкритих задач.* _Ви можете створити нову задачу, натиснувши кнопку '🆕 Створити задачу'._",  # noqa: E501
                reply_markup=main_menu_markup,
                parse_mode="Markdown",
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
            active_mark = (
                "➡️ " if issue["key"] == context.user_data.get("active_task") else ""
            )
            text_list.append(f"{active_mark}*`{issue['key']}`* — _{issue['status']}_")

        text_list.append(
            "\n_Щоб додати коментар до активної задачі, просто напишіть текст._"
        )

        # Виводимо список з форматуванням Markdown
        await update.message.reply_text(
            "\n".join(text_list), reply_markup=issues_view_markup, parse_mode="Markdown"
        )

        # Викликаємо функцію для показу детальної інформації про активну задачу
        if not await show_active_task_details(update, context):
            logger.error("Не вдалося показати деталі задачі")
            await update.message.reply_text(
                "❌ *Не вдалося отримати деталі задачі. Будь ласка, спробуйте ще раз.*",
                reply_markup=issues_view_markup,
                parse_mode="Markdown",
            )

    except Exception as e:
        logger.error(f"Помилка при оновленні статусів задач: {str(e)}")
        await update.message.reply_text(
            f"❌ *Помилка при оновленні статусів:* _{str(e)}_",
            reply_markup=issues_view_markup,
            parse_mode="Markdown",
        )


async def return_to_main_from_conversation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Обробник для кнопки 'Вийти на головну' з ConversationHandler"""
    # Очищаємо дані конверсації
    context.user_data.pop("full_name", None)
    context.user_data.pop("mobile_number", None)
    context.user_data.pop("division", None)
    context.user_data.pop("department", None)
    context.user_data.pop("service", None)
    context.user_data.pop("description", None)
    context.user_data.pop("attached_photo", None)
    context.user_data.pop(
        "in_conversation", None
    )  # КРИТИЧНО: очищаємо флаг conversation

    await update.message.reply_text(
        "🏠 *Головне меню*", reply_markup=main_menu_markup, parse_mode="Markdown"
    )
    return ConversationHandler.END


async def return_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник для кнопки 'Вийти на головну' з режиму перегляду задач"""
    # Очищаємо непотрібні дані
    if context.user_data and "last_issues_list" in context.user_data:
        del context.user_data["last_issues_list"]

    await update.message.reply_text(
        "🏠", reply_markup=main_menu_markup, parse_mode="Markdown"
    )


async def handle_back_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глобальний обробник для кнопки '🔙 Назад'"""
    # Очищаємо флаг conversation якщо він є
    context.user_data.pop("in_conversation", None)

    # Повертаємо на головне меню
    await update.message.reply_text(
        "🏠 *Головне меню*", reply_markup=main_menu_markup, parse_mode="Markdown"
    )


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
            parse_mode="Markdown",
        )


async def comment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Автоматично додає коментар до відкритої задачі"""
    logger.info(
        f"comment_handler викликано! Текст повідомлення: '{update.message.text}'"
    )

    # ПЕРЕВІРКА 1: якщо користувач у процесі реєстрації, НЕ обробляємо
    registration_step = context.user_data.get("registration_step")
    if registration_step:
        logger.info(
            f"comment_handler: користувач у процесі реєстрації (крок: {registration_step}), ігноруємо це повідомлення"
        )
        return  # Просто виходимо, не обробляємо

    # ВИДАЛЕНО ПЕРЕВІРКУ 2: in_conversation
    # ConversationHandler має вищий пріоритет (group=-1) і обробить повідомлення раніше
    # Якщо ConversationHandler завершився, то comment_handler має право обробляти повідомлення

    # Перевіряємо, чи це не кнопка
    text = update.message.text
    logger.info(f"comment_handler: перевіряємо текст: '{text}'")

    if text in [
        "🧾 Мої задачі",
        "🆕 Створити задачу",
        "ℹ️ Допомога",
        "🔄 Повторити /start",
        "🔄 Оновити статус задачі",
        "✅ Перевірити статус задачі",
        "🔙 Назад",
        "🏠 Вийти на головну",
    ]:
        # Це кнопка, пропускаємо
        logger.info("comment_handler: це кнопка, пропускаємо обробку")
        return  # Просто виходимо

    logger.info("comment_handler: це не кнопка, продовжуємо обробку коментаря")

    # Перевіряємо, чи користувач має відкриті задачі
    tg_id = str(update.effective_user.id)
    open_issues = await find_open_issues(tg_id)

    if not open_issues:
        # ВИДАЛЕНО: це повідомлення тепер обробляється новим диспетчером
        # Просто виходимо без повідомлення, щоб інші обробники могли спрацювати
        logger.info(
            f"comment_handler: у користувача {tg_id} немає відкритих задач, пропускаємо"
        )
        return

    # Автоматично встановлюємо першу відкриту задачу як активну
    key = open_issues[0]["key"]
    context.user_data["active_task"] = key
    logger.info(f"Автоматично встановлено активну задачу: {key}")

    # Перевіряємо статус задачі перед додаванням коментаря
    try:
        status_info = await get_issue_status(key)
        status_category = status_info.get("category", "")
        status_name = status_info.get("name", "")

        logger.info(
            f"🔍 Статус задачі {key}: {status_name} (категорія: {status_category})"
        )

        # Якщо задача закрита (статус категорія "Done" або "Готово"), забороняємо додавання коментарів
        if status_category in ["Done", "Готово"]:
            logger.warning(
                f"🚫 Спроба додати коментар до закритої задачі {key} зі статусом {status_name}"
            )

            # Очищаємо поточну задачу користувача
            clear_user_current_task(int(tg_id))

            # Оновлюємо стан користувача на AUTHORIZED_NO_TASKS
            set_user_bot_state(int(tg_id), BotState.AUTHORIZED_NO_TASKS)

            await update.message.reply_text(
                f"❌ Задача *{key}* вже завершена (статус: _{status_name}_)\\.\n"
                f"Неможливо додавати коментарі до закритих задач\\.\n\n"
                f"📝 Для створення нової задачі просто опишіть проблему\\.",
                parse_mode="MarkdownV2",
                reply_markup=main_menu_markup,
            )
            return

    except Exception as e:
        logger.error(f"Помилка перевірки статусу задачі {key}: {e}")
        await update.message.reply_text("❌ Помилка перевірки статусу задачі")
        return

    if not text or text.strip() == "":
        await update.message.reply_text(
            "❌ *Коментар не може бути пустим.*",
            reply_markup=issues_view_markup,
            parse_mode="Markdown",
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

        logger.info(
            f"Додавання коментаря до задачі {key} від {author_name or 'невідомого користувача'}: '{text[:20]}...'"
        )
        await add_comment_to_jira(key, text, author_name)

        # Додаємо повідомлення до кешу, щоб уникнути дублікатів при отриманні вебхуку
        from src.jira_webhooks2 import add_message_to_cache

        formatted_message = text
        add_message_to_cache(key, formatted_message)

        # Підтвердження користувачу (webhook може не спрацювати для коментарів від бота)
        await update.message.reply_text(
            f"✅ Коментар додано до задачі *{key}*",
            reply_markup=main_menu_markup,
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Помилка додавання коментаря до {key}: {str(e)}")
        await update.message.reply_text(
            f"❌ *Помилка додавання коментаря до задачі {key}*:\n_{str(e)}_",
            reply_markup=issues_view_markup,
            parse_mode="Markdown",
        )


async def file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробляє будь-яке вкладення і прикріплює до активної задачі"""
    # Отримуємо поточну задачу з bot_state
    telegram_id = update.message.from_user.id
    key = get_user_current_task(telegram_id)

    # Якщо не знайдено в bot_state, перевіряємо старий спосіб (для сумісності)
    if not key:
        key = context.user_data.get("active_task")

    if not key:
        await update.message.reply_text(
            "❗ *Спершу створіть або виберіть задачу.*",
            reply_markup=issues_view_markup,
            parse_mode="Markdown",
        )
        return

    # Перевіряємо статус задачі перед прикріпленням файлу
    try:
        status_info = await get_issue_status(key)
        status_category = status_info.get("category", "")
        status_name = status_info.get("name", "")

        logger.info(
            f"🔍 Статус задачі {key}: {status_name} (категорія: {status_category})"
        )

        # Якщо задача закрита (статус категорія "Done" або "Готово"), забороняємо прикріплення файлів
        if status_category in ["Done", "Готово"]:
            logger.warning(
                f"🚫 Спроба прикріпити файл до закритої задачі {key} зі статусом {status_name}"
            )

            # Очищаємо поточну задачу користувача
            telegram_id = update.message.from_user.id
            clear_user_current_task(telegram_id)

            # Оновлюємо стан користувача на AUTHORIZED_NO_TASKS
            set_user_bot_state(telegram_id, BotState.AUTHORIZED_NO_TASKS)

            await update.message.reply_text(
                f"❌ Задача *{key}* вже завершена (статус: _{status_name}_)\\.\n"
                f"Неможливо прикріпляти файли до закритих задач\\.\n\n"
                f"📝 Для створення нової задачі просто опишіть проблему\\.",
                parse_mode="MarkdownV2",
                reply_markup=main_menu_markup,
            )
            return

    except Exception as e:
        logger.error(f"Помилка перевірки статусу задачі {key}: {e}")
        await update.message.reply_text("❌ Помилка перевірки статусу задачі")
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
        await update.message.reply_text(
            "❌ *Невідомий тип файлу.*",
            reply_markup=issues_view_markup,
            parse_mode="Markdown",
        )
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
                    logger.info(
                        f"ПІБ отримано з Google Sheets для файлу: {author_name}"
                    )
            except Exception as e:
                logger.warning(
                    f"Не вдалось отримати ПІБ з Google Sheets для файлу: {e}"
                )

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
        file_comment = (
            ""  # Порожній текст, але заголовок автора буде додано автоматично
        )
        await add_comment_with_file_reference_to_jira(
            key, file_comment, author_name_str, filename, bytes(file_bytes)
        )
        logger.info(
            f"Коментар з файлом та посиланням від {author_name_str} додано до {key}"
        )

        # Додаємо інформацію про файл до кешу (simplified without tech support header)
        from src.jira_webhooks2 import add_message_to_cache

        formatted_file_message = f"Прикріплено файл: {filename}"
        add_message_to_cache(key, formatted_file_message)

        # Повідомляємо користувача про успішне прикріплення
        if caption and caption.strip():
            await update.message.reply_text(
                f"✅ Коментар і файл '`{filename}`' з посиланням додано до *{key}*.",
                reply_markup=reply_markup,
                parse_mode="Markdown",
            )
            logger.info(
                f"Коментар з текстом і файл '{filename}' з посиланням успішно додано до задачі {key}"
            )
        else:
            await update.message.reply_text(
                f"✅ Файл '`{filename}`' з посиланням прикріплено до *{key}*.",
                reply_markup=reply_markup,
                parse_mode="Markdown",
            )
            logger.info(
                f"Файл '{filename}' з посиланням успішно додано до задачі {key}"
            )

    except Exception as e:
        error_message = str(e)
        logger.error(f"Помилка при прикріпленні файлу до {key}: {error_message}")
        await update.message.reply_text(
            f"❌ *Помилка:* файл не відправлено. _{error_message}_",
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )


async def check_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Перевірити статус активної задачі"""
    key = context.user_data.get("active_task")
    if not key:
        await update.message.reply_text(
            "❗ *Немає активної задачі.*",
            reply_markup=issues_view_markup,
            parse_mode="Markdown",
        )
        return

    try:
        # Отримуємо повні деталі задачі з Jira
        issue = await get_full_issue_info(key)

        # Перевіряємо, чи задача виконана (статус Done)
        if (
            issue.get("status", "").lower() == "done"
            or issue.get("statusCategory", "").lower() == "done"
        ):
            # Якщо задача виконана, показуємо відповідне повідомлення і повертаємо до головного меню
            await update.message.reply_text(
                f"*Статуси оновлено. Ваша задача:*\n➡️ *`{key}`* — *Виконана*.\n\n"
                f"*Можете створити нову задачу, натиснувши відповідну кнопку в меню:*",
                parse_mode="Markdown",
            )

            # Надсилаємо додаткове повідомлення з клавіатурою головного меню
            await update.message.reply_text(
                "🏠 *Головне меню*",
                reply_markup=main_menu_markup,
                parse_mode="Markdown",
            )

            # Очищаємо активну задачу
            context.user_data.pop("active_task", None)
            return

        # Используем модуль форматирования для единообразного отображения
        from src.fixed_issue_formatter import format_issue_info, format_issue_text

        # Получаем отформатированные данные
        formatted_issue = format_issue_info(issue)

        # Формируем текст и добавляем защиту от разбивки на символы
        text = format_issue_text(formatted_issue)

        # Добавляем маркер невидимого пробела в начало текста, чтобы предотвратить разбиение на символы
        text = "\u200b" + text

        logger.info(
            f"Перевірка статусу задачі {key}: {issue.get('status', 'Невідомо')}"
        )
        await update.message.reply_text(
            text,
            reply_markup=issues_view_markup,
            parse_mode=None,  # Отключаем парсинг Markdown/HTML для предотвращения проблем с форматированием
        )
    except Exception as e:
        logger.error(f"Помилка отримання статусу задачі {key}: {str(e)}")
        await update.message.reply_text(
            f"❌ *Помилка отримання статусу задачі* `{key}`.",
            reply_markup=issues_view_markup,
            parse_mode="Markdown",
        )


async def create_issue_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Початок створення задачі"""
    # 🔥 Встановлюємо флаг активного conversation для блокування інших handlers
    context.user_data["in_conversation"] = True

    # Універсальна функція для роботи з message і callback_query
    async def send_message(text, reply_markup=None, parse_mode=None):
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(
                text, reply_markup=reply_markup, parse_mode=parse_mode
            )
        else:
            await update.message.reply_text(
                text, reply_markup=reply_markup, parse_mode=parse_mode
            )

    # Отримуємо текст з message або callback_query
    message_text = None
    if update.message and update.message.text:
        message_text = update.message.text
    elif update.callback_query and update.callback_query.data:
        message_text = update.callback_query.data

    logger.info(f"create_issue_start викликано! Текст повідомлення: '{message_text}'")

    # Перевіряємо чи це автоматичне створення задачі з довільного тексту
    auto_create = context.user_data.get("skip_description", False)

    # ✅ Якщо це кнопкове створення, очищаємо залишки від попереднього автоматичного створення
    if message_text in ["🆕 Створити задачу", "CREATE_ISSUE"] and not auto_create:
        context.user_data.pop("issue_description", None)
        context.user_data.pop("skip_description", None)
        logger.info("Кнопкове створення: очищено issue_description та skip_description")

    # Додаткова перевірка на точний текст кнопки (тільки якщо не автоматичне створення)
    if (
        not auto_create
        and message_text
        and message_text not in ["🆕 Створити задачу", "CREATE_ISSUE"]
    ):
        logger.warning(
            f"create_issue_start викликано з неочікуваним текстом: '{message_text}'"
        )
        return ConversationHandler.END

    # Завантажуємо профіль користувача якщо він не в контексті
    profile = context.user_data.get("profile")
    if not profile:
        from src.user_state_service import load_user_profile

        tg_id = update.effective_user.id
        profile = load_user_profile(tg_id)
        if profile:
            context.user_data["profile"] = profile

    tg_id = str(update.effective_user.id)
    logger.info(f"create_issue_start: tg_id={tg_id}")

    # Перевірка на відкриті задачі (тільки якщо не автоматичне створення)
    if not auto_create:
        open_issues = await find_open_issues(tg_id)
        if open_issues:
            key = open_issues[0]["key"]
            status = open_issues[0]["status"]
            await send_message(
                f"У вас є відкрита задача *`{key}`* (статус: _{status}_).\n"
                "_Спочатку дочекайтесь її вирішення або додайте коментар до існуючої._",
                reply_markup=issues_view_markup,
                parse_mode="Markdown",
            )
            return ConversationHandler.END

    # Якщо користувач авторизований - беремо дані з профілю та переходимо одразу до вибору сервісу
    if profile and profile.get("division") and profile.get("department"):
        # Копируем все необходимые данные из профиля пользователя
        context.user_data.update(
            {
                "full_name": profile["full_name"],
                "division": profile["division"],
                "department": profile["department"],
                "mobile_number": profile.get("mobile_number", ""),
                "telegram_id": profile["telegram_id"],
                "telegram_username": profile.get("telegram_username", ""),
                "account_id": profile.get("account_id"),
            }
        )
        logger.info(
            f"Авторизований користувач {profile['full_name']} з повними даними, переходимо до вибору сервісу"
        )

        # Переходимо до вибору сервісу напряму
        await send_message(
            "*Оберіть сервіс:*",
            reply_markup=service_selection_markup(SERVICES),
            parse_mode="Markdown",
        )
        return SERVICE
    elif profile:
        # Користувач авторизований, але в нього неповні дані - доповнюємо їх
        logger.info(
            f"Авторизований користувач {profile['full_name']}, але потрібно доповнити дані профілю"
        )
        context.user_data.update(
            {
                "full_name": profile["full_name"],
                "mobile_number": profile.get("mobile_number", ""),
                "telegram_id": profile["telegram_id"],
                "telegram_username": profile.get("telegram_username", ""),
                "account_id": profile.get("account_id"),
            }
        )

        # Перевіряємо що саме відсутнє
        if not profile.get("division"):
            await send_message(
                "*Оберіть ваш підрозділ:*",
                reply_markup=ReplyKeyboardMarkup(
                    [[div] for div in DIVISIONS] + [["🔙 Назад"]],
                    resize_keyboard=True,
                    one_time_keyboard=True,
                ),
                parse_mode="Markdown",
            )
            return DIVISION
        elif not profile.get("department"):
            context.user_data["division"] = profile["division"]
            await send_message(
                "*Оберіть ваш департамент:*",
                reply_markup=ReplyKeyboardMarkup(
                    [[dept] for dept in DEPARTMENTS] + [["🔙 Назад"]],
                    resize_keyboard=True,
                    one_time_keyboard=True,
                ),
                parse_mode="Markdown",
            )
            return DEPARTMENT
    else:
        # Для неавторизованого користувача - спочатку запитуємо ПІБ
        await send_message(
            "*Будь ласка, введіть ваше повне ім'я:*",
            reply_markup=main_menu_markup,
            parse_mode="Markdown",
        )
        logger.info(f"Переход к FULL_NAME для неавторизованого tg_id={tg_id}")
        return FULL_NAME


async def full_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка введеного ПІБ для неавторизованого користувача"""
    full_name = update.message.text.strip()
    tg_id = str(update.effective_user.id)
    logger.info(f"full_name_handler вызван, получено имя: '{full_name}', tg_id={tg_id}")

    # � Встановлюємо флаг активного conversation для блокування інших handlers
    context.user_data["in_conversation"] = True

    # �🔍 КРИТИЧНА ПЕРЕВІРКА: Якщо отримали кнопку з головного меню, завершуємо ConversationHandler
    if check_main_menu_button_and_exit(full_name, context, update):
        await update.message.reply_text(
            "🔄 *Повернення до головного меню*\n\n"
            "Для створення нової задачі натисніть *'🆕 Створити задачу'*.",
            reply_markup=main_menu_markup,
            parse_mode="Markdown",
        )
        context.user_data.pop("in_conversation", None)  # Очищаємо флаг
        return ConversationHandler.END

    if len(full_name) < 2:
        await update.message.reply_text(
            "❌ *Ім'я занадто коротке.* _Будь ласка, введіть ваше повне ім'я:_",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown",
        )
        return FULL_NAME

    context.user_data["full_name"] = full_name
    logger.info(f"Збережено ім'я користувача: {full_name}")

    # Запитуємо номер телефону з чітким повідомленням про обов'язковість авторизації
    await update.message.reply_text(
        "📞 *Для продовження необхідна авторизація!*\n\n"
        "⚠️ *Увага:* Без авторизації бот не працює і не створює задачі в Jira.\n\n"
        "🔐 *Натисніть кнопку нижче* '📞 Надати номер телефону' для авторизації:",
        reply_markup=contact_request_markup,
        parse_mode="Markdown",
    )
    logger.info(f"Перехід до MOBILE_NUMBER для tg_id={tg_id}")
    return MOBILE_NUMBER


async def remind_to_use_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Нагадує користувачу натиснути кнопку для надання контакту"""
    await update.message.reply_text(
        "⚠️ *Будь ласка, натисніть кнопку нижче* для надання контакту.\n\n"
        "📱 Просто введення тексту не працює - потрібно натиснути кнопку "
        "*'📞 Надати номер телефону'*",
        reply_markup=contact_request_markup,
        parse_mode="Markdown",
    )
    logger.info(
        f"remind_to_use_button: нагадав користувачу {update.effective_user.id} натиснути кнопку"
    )
    return MOBILE_NUMBER


async def reject_any_action_during_auth(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Відхиляє будь-які дії (фото, відео, документи, стікери тощо) під час авторизації"""

    # Визначаємо тип медіа
    media_type = "медіафайл"
    if update.message.photo:
        media_type = "фото"
    elif update.message.video:
        media_type = "відео"
    elif update.message.document:
        media_type = "документ"
    elif update.message.sticker:
        media_type = "стікер"
    elif update.message.voice:
        media_type = "голосове повідомлення"
    elif update.message.audio:
        media_type = "аудіо"
    elif update.message.video_note:
        media_type = "відеоповідомлення"

    await update.message.reply_text(
        f"❌ *Не можна відправляти {media_type} під час авторизації!*\n\n"
        "📞 Будь ласка, натисніть кнопку нижче '📞 Надати номер телефону' для авторизації.\n\n"
        "⚠️ *Увага:* Без авторизації бот не працює і не створює задачі.",
        reply_markup=contact_request_markup,
        parse_mode="Markdown",
    )
    logger.info(
        f"reject_any_action_during_auth: відхилено {media_type} від користувача {update.effective_user.id}"
    )
    return MOBILE_NUMBER


async def global_awaiting_auth_text_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """
    Глобальний handler для текстових повідомлень ДО авторизації.
    Спрацьовує якщо користувач НЕ авторизований і намагається відправити текст.
    """
    telegram_id = update.effective_user.id

    # Перевіряємо чи користувач авторизований
    user_data, _ = await user_manager.find_user_comprehensive(telegram_id)

    # 🔥 ВАЖЛИВО: Якщо користувач в процесі реєстрації - НЕ показуємо попередження
    registration_step = context.user_data.get("registration_step")
    if registration_step:
        # Користувач вже в процесі реєстрації, не треба його відволікати
        logger.info(
            f"global_awaiting_auth_text_handler: користувач {telegram_id} "
            f"в процесі реєстрації (крок: {registration_step}), пропускаємо"
        )
        return

    if not user_data and not context.user_data.get("profile"):
        # Користувач НЕ авторизований - показуємо повідомлення
        await update.message.reply_text(
            "⚠️ *Будь ласка, натисніть кнопку нижче* для надання контакту.\n\n"
            "📱 Просто введення тексту не працює - потрібно натиснути кнопку "
            "*'📞 Надати номер телефону'*\n\n"
            "⚠️ *Увага:* Без авторизації бот не працює.",
            reply_markup=contact_request_markup,
            parse_mode="Markdown",
        )
        logger.info(
            f"global_awaiting_auth_text_handler: нагадав неавторизованому користувачу {telegram_id} натиснути кнопку"
        )


async def global_awaiting_auth_media_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """
    Глобальний handler для медіафайлів ДО авторизації.
    Спрацьовує якщо користувач НЕ авторизований і намагається відправити медіа.
    """
    telegram_id = update.effective_user.id

    # Перевіряємо чи користувач авторизований
    user_data, _ = await user_manager.find_user_comprehensive(telegram_id)

    # 🔥 ВАЖЛИВО: Якщо користувач в процесі реєстрації - НЕ показуємо попередження
    registration_step = context.user_data.get("registration_step")
    if registration_step:
        # Користувач вже в процесі реєстрації, не треба його відволікати
        logger.info(
            f"global_awaiting_auth_media_handler: користувач {telegram_id} "
            f"в процесі реєстрації (крок: {registration_step}), пропускаємо"
        )
        return

    if not user_data and not context.user_data.get("profile"):
        # Визначаємо тип медіа
        media_type = "медіафайл"
        if update.message.photo:
            media_type = "фото"
        elif update.message.video:
            media_type = "відео"
        elif update.message.document:
            media_type = "документ"
        elif update.message.sticker:
            media_type = "стікер"
        elif update.message.voice:
            media_type = "голосове повідомлення"
        elif update.message.audio:
            media_type = "аудіо"
        elif update.message.video_note:
            media_type = "відеоповідомлення"

        # Користувач НЕ авторизований - показуємо повідомлення
        await update.message.reply_text(
            f"❌ *Не можна відправляти {media_type} без авторизації!*\n\n"
            "📞 Будь ласка, натисніть кнопку нижче '📞 Надати номер телефону' для авторизації.\n\n"
            "⚠️ *Увага:* Без авторизації бот не працює і не створює задачі.",
            reply_markup=contact_request_markup,
            parse_mode="Markdown",
        )
        logger.info(
            f"global_awaiting_auth_media_handler: відхилено {media_type} від неавторизованого користувача {telegram_id}"
        )


async def division_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка вибраного підрозділу"""
    text = update.message.text

    # 🔍 КРИТИЧНА ПЕРЕВІРКА: Якщо отримали кнопку з головного меню, завершуємо ConversationHandler
    if text and check_main_menu_button_and_exit(text, context, update):
        await update.message.reply_text(
            "🔄 *Повернення до головного меню*\n\n"
            "Для створення нової задачі натисніть *'🆕 Створити задачу'*.",
            reply_markup=main_menu_markup,
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    # Обробка кнопки "🔙 Назад"
    if text == "🔙 Назад":
        # Повертаємо на головний екран і завершуємо ConversationHandler
        await update.message.reply_text(
            "🏠 *Головне меню*", reply_markup=main_menu_markup, parse_mode="Markdown"
        )
        return ConversationHandler.END

    # Перевірка наявності збереженого імені
    if not context.user_data.get("full_name"):
        await update.message.reply_text(
            "*Будь ласка, спочатку введіть ваше повне ім'я:*",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown",
        )
        return FULL_NAME

    context.user_data["division"] = text
    logger.info(f"Збережено підрозділ: {text}")

    # Запит департаменту
    markup = ReplyKeyboardMarkup(
        [[dept] for dept in DEPARTMENTS] + [["🔙 Назад"]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await update.message.reply_text(
        "*Оберіть ваш департамент:*", reply_markup=markup, parse_mode="Markdown"
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
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    if text == "🔙 Назад":
        # Повертаємо на головний екран і завершуємо ConversationHandler
        await update.message.reply_text(
            "🏠 *Головне меню*", reply_markup=main_menu_markup, parse_mode="Markdown"
        )
        return ConversationHandler.END

    context.user_data["department"] = text

    # Переходимо до вибору сервісу
    await update.message.reply_text(
        "*Оберіть сервіс:*",
        reply_markup=service_selection_markup(SERVICES),
        parse_mode="Markdown",
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
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    if text == "🔙 Назад":
        # Повертаємо на головний екран і завершуємо ConversationHandler
        await update.message.reply_text(
            "🏠 *Головне меню*", reply_markup=main_menu_markup, parse_mode="Markdown"
        )
        return ConversationHandler.END

    # Перевіряємо чи вибраний сервіс є в списку валідних сервісів
    if text not in SERVICES:
        logger.warning(f"Невалідний сервіс: '{text}'. Доступні сервіси: {SERVICES}")
        await update.message.reply_text(
            "❌ *Невалідний вибір сервісу.*\n\n" "*Оберіть сервіс зі списку:*",
            reply_markup=service_selection_markup(SERVICES),
            parse_mode="Markdown",
        )
        return SERVICE  # Залишаємось в тому ж стані

    logger.info(f"Користувач вибрав валідний сервіс: '{text}'")
    context.user_data["service"] = text

    # Перевіряємо чи є вже готовий опис (для автоматичного створення)
    if context.user_data.get("issue_description"):
        logger.info("Опис вже є з автоматичного створення, пропускаємо збір опису")
        # Переміщаємо опис з issue_description до description
        context.user_data["description"] = context.user_data["issue_description"]
        context.user_data.pop("issue_description", None)
        context.user_data.pop("skip_description", None)

        # Викликаємо логіку створення задачі з description_handler
        await create_issue_automatically(update, context)
        return ConversationHandler.END

    await update.message.reply_text(
        "*Опишіть проблему у кілька речень:*",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown",
    )
    return DESCRIPTION


async def create_issue_automatically(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Автоматично створює задачу з наявними даними"""
    await update.message.reply_text("📝 *Створюємо задачу...*", parse_mode="Markdown")

    # Створюємо задачу автоматично
    try:
        bot_vars = context.user_data.copy()

        # Формуємо опис для задачі
        task_description = (
            f"ПІБ: {bot_vars.get('full_name', '')}\n"
            f"Підрозділ: {bot_vars.get('division', '')}\n"
            f"Департамент: {bot_vars.get('department', '')}\n"
            f"Сервіс: {bot_vars.get('service', '')}\n"
            f"Опис: {bot_vars.get('description', '')}"
        )

        # Додаємо поля проекта та типа задачі, якщо їх немає
        if "issuetype" not in bot_vars:
            bot_vars["issuetype"] = JIRA_ISSUE_TYPE

        if "project" not in bot_vars:
            bot_vars["project"] = JIRA_PROJECT_KEY

        # Додаємо summary та description
        bot_vars["summary"] = (
            f"{bot_vars.get('service', 'Загальний')}: {bot_vars.get('description', '')[:50]}"
        )
        bot_vars["description"] = task_description

        # Додаємо telegram fields для JIRA
        if not bot_vars.get("telegram_id"):
            bot_vars["telegram_id"] = str(update.effective_user.id)

        username = update.effective_user.username
        if username:
            bot_vars["telegram_username"] = username
        elif "telegram_username" in bot_vars:
            del bot_vars["telegram_username"]

        # Додаємо аккаунт репортера, якщо є
        if bot_vars.get("account_id") is None and JIRA_REPORTER_ACCOUNT_ID:
            bot_vars["account_id"] = JIRA_REPORTER_ACCOUNT_ID

        # Використовуємо функцію build_jira_payload
        from src.services import build_jira_payload
        from src.constants import (
            DIVISION_ID_MAPPINGS,
            DEPARTMENT_ID_MAPPINGS,
            SERVICE_ID_MAPPINGS,
        )

        if "division" in bot_vars and bot_vars["division"] in DIVISION_ID_MAPPINGS:
            field_id = JIRA_FIELD_IDS["division"]
            bot_vars[field_id] = {
                "id": DIVISION_ID_MAPPINGS[bot_vars["division"]]["id"]
            }

        if (
            "department" in bot_vars
            and bot_vars["department"] in DEPARTMENT_ID_MAPPINGS
        ):
            field_id = JIRA_FIELD_IDS["department"]
            bot_vars[field_id] = {
                "id": DEPARTMENT_ID_MAPPINGS[bot_vars["department"]]["id"]
            }

        if "service" in bot_vars and bot_vars["service"] in SERVICE_ID_MAPPINGS:
            field_id = JIRA_FIELD_IDS["service"]
            bot_vars[field_id] = {"id": SERVICE_ID_MAPPINGS[bot_vars["service"]]["id"]}

        payload = build_jira_payload(bot_vars)

        # Створюємо задачу в JIRA
        issue_key = await create_jira_issue(payload)

        # Встановлюємо активну задачу
        context.user_data["active_task"] = issue_key

        # Оновлюємо стан користувача - тепер у нього є відкрита задача
        telegram_id = update.effective_user.id
        set_user_current_task(telegram_id, issue_key)
        logger.info(
            f"🔄 Стан користувача {telegram_id} змінено на AUTHORIZED_WITH_TASK з задачею {issue_key}"
        )

        # Очищаємо тимчасові дані
        context.user_data.pop("in_conversation", None)  # ✅ Очищаємо флаг ПЕРЕД clear()
        context.user_data.clear()
        context.user_data["active_task"] = issue_key
        context.user_data["telegram_id"] = str(telegram_id)

        await update.message.reply_text(
            f"✅ *Задача створена!*\n\n"
            f"🎫 *Номер задачі:* `{issue_key}`\n"
            f"📝 *Опис:* {bot_vars.get('description', '')[:100]}{'...' if len(bot_vars.get('description', '')) > 100 else ''}\n\n"  # noqa: E501
            f"💬 *Тепер ви можете додавати коментарі до цієї задачі, просто написавши повідомлення.*",
            reply_markup=main_menu_markup,
            parse_mode="Markdown",
        )

    except Exception as e:
        logger.error(f"Помилка створення задачі: {str(e)}")
        await update.message.reply_text(
            f"❌ *Помилка створення задачі:*\n_{str(e)}_\n\n"
            f"Спробуйте ще раз або зверніться до адміністратора.",
            reply_markup=main_menu_markup,
            parse_mode="Markdown",
        )


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
                parse_mode="Markdown",
            )
            return ConversationHandler.END

    # Обробляємо як текст, так і фото з підписом
    if update.message.photo:
        # Якщо користувач відправив фото
        description = update.message.caption or ""
        if not description.strip():
            await update.message.reply_text(
                "❌ *Помилка:* Будь ласка, додайте опис проблеми в підпис до фото.",
                parse_mode="Markdown",
            )
            return DESCRIPTION

        # Зберігаємо фото для подальшого прикріплення до задачі
        photo = update.message.photo[-1]  # Беремо найбільшу версію фото
        context.user_data["attached_photo"] = {
            "file_id": photo.file_id,
            "file_unique_id": photo.file_unique_id,
            "caption": description,
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
                parse_mode="Markdown",
            )
            return DESCRIPTION
        context.user_data["description"] = description

    # 🚀 НОВА ЛОГІКА: Автоматичне створення задачі одразу після опису
    await update.message.reply_text(
        "📝 *Опис збережено! Створюємо задачу...*", parse_mode="Markdown"
    )

    # Створюємо задачу автоматично
    try:
        bot_vars = context.user_data.copy()

        # Формуємо опис для задачі
        task_description = (
            f"ПІБ: {bot_vars.get('full_name', '')}\n"
            f"Підрозділ: {bot_vars.get('division', '')}\n"
            f"Департамент: {bot_vars.get('department', '')}\n"
            f"Сервіс: {bot_vars.get('service', '')}\n"
            f"Опис: {bot_vars.get('description', '')}"
        )

        # Додаємо поля проекта та типа задачі, якщо їх немає
        if "issuetype" not in bot_vars:
            bot_vars["issuetype"] = JIRA_ISSUE_TYPE

        if "project" not in bot_vars:
            bot_vars["project"] = JIRA_PROJECT_KEY

        # Додаємо summary та description
        bot_vars["summary"] = (
            f"{bot_vars.get('service', 'Загальний')}: {bot_vars.get('description', '')[:50]}"
        )
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
        from src.constants import (
            DIVISION_ID_MAPPINGS,
            DEPARTMENT_ID_MAPPINGS,
            SERVICE_ID_MAPPINGS,
        )

        if "division" in bot_vars and bot_vars["division"] in DIVISION_ID_MAPPINGS:
            field_id = JIRA_FIELD_IDS["division"]
            bot_vars[field_id] = {
                "id": DIVISION_ID_MAPPINGS[bot_vars["division"]]["id"]
            }
            logger.info(
                f"Додано маппінг для division: {bot_vars['division']} -> {bot_vars[field_id]}"
            )

        if (
            "department" in bot_vars
            and bot_vars["department"] in DEPARTMENT_ID_MAPPINGS
        ):
            field_id = JIRA_FIELD_IDS["department"]
            bot_vars[field_id] = {
                "id": DEPARTMENT_ID_MAPPINGS[bot_vars["department"]]["id"]
            }
            logger.info(
                f"Додано маппінг для department: {bot_vars['department']} -> {bot_vars[field_id]}"
            )

        if "service" in bot_vars and bot_vars["service"] in SERVICE_ID_MAPPINGS:
            field_id = JIRA_FIELD_IDS["service"]
            bot_vars[field_id] = {"id": SERVICE_ID_MAPPINGS[bot_vars["service"]]["id"]}
            logger.info(
                f"Додано маппінг для service: {bot_vars['service']} -> {bot_vars[field_id]}"
            )

        payload = build_jira_payload(bot_vars)

        # Логування для діагностики telegram_id
        logger.info(
            f"🔍 ДІАГНОСТИКА: Створення задачі з telegram_id={bot_vars.get('telegram_id')} та username={bot_vars.get('telegram_username')}"  # noqa: E501
        )
        logger.info(
            f"🔍 Payload fields містить telegram_id: {'telegram_id' in str(payload)}"
        )

        # Створюємо задачу в JIRA
        issue_key = await create_jira_issue(payload)

        # Встановлюємо активну задачу (відновлено з confirm_callback)
        context.user_data["active_task"] = issue_key

        # Оновлюємо стан користувача - тепер у нього є відкрита задача
        telegram_id = update.effective_user.id
        set_user_current_task(telegram_id, issue_key)
        logger.info(
            f"🔄 Стан користувача {telegram_id} змінено на AUTHORIZED_WITH_TASK з задачею {issue_key}"
        )

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

                # ВИДАЛЕНО: Дублювання з webhook повідомленням про створення задачі
                # await update.message.reply_text(
                #     f"✅ *Задача створена:* `{issue_key}`\n"
                #     f"📸 *Фото прикріплено успішно*\n\n"
                #     f"_Тепер ви можете додати коментар або прикріпити інші файли._",
                #     reply_markup=issues_view_markup,
                #     parse_mode="Markdown"
                # )
            except Exception as e:
                logger.error(
                    f"Помилка прикріплення фото до задачі {issue_key}: {str(e)}"
                )
                # ВИДАЛЕНО: Дублювання з webhook повідомленням про створення задачі
                # await update.message.reply_text(
                #     f"✅ *Задача створена:* `{issue_key}`\n"
                #     f"❌ *Помилка прикріплення фото:* _{str(e)}_\n\n"
                #     f"_Ви можете спробувати прикріпити фото знову через коментарі._",
                #     reply_markup=issues_view_markup,
                #     parse_mode="Markdown"
                # )
        else:
            # ВИДАЛЕНО: Дублювання з webhook повідомленням про створення задачі
            # await update.message.reply_text(
            #     f"✅ *Задача створена:* `{issue_key}`\n\n"
            #     f"_Тепер ви можете додати коментар або прикріпити файл._",
            #     reply_markup=issues_view_markup,
            #     parse_mode="Markdown"
            # )
            pass  # Webhook вже надішле повідомлення про створення задачі

        # Очищаємо дані conversation після успішного створення
        conversation_keys = [
            "full_name",
            "mobile_number",
            "division",
            "department",
            "service",
            "description",
            "attached_photo",
            "in_conversation",
        ]
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
                error_message = (
                    "Вказано невірний тип задачі. Будь ласка, виберіть правильний тип."
                )
            elif "project" in error_message.lower():
                error_message = (
                    "Вказано невірний проект. Будь ласка, виберіть правильний проект."
                )

        logger.error(f"Помилка API Jira при створенні задачі: {str(e)}")
        await update.message.reply_text(
            f"❌ *Помилка створення задачі:* _{error_message}_",
            reply_markup=issues_view_markup,
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Невідома помилка при створенні задачі: {str(e)}")
        await update.message.reply_text(
            "❌ *Помилка створення задачі.* _Будь ласка, спробуйте пізніше або зв'яжіться з адміністратором._",
            reply_markup=issues_view_markup,
            parse_mode="Markdown",
        )
        return ConversationHandler.END


async def confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка натискання Створити задачу або Назад"""
    query = update.callback_query
    await query.answer()
    if query.data == "BACK_TO_SERVICE":
        # Повернутися до вибору сервісу
        await query.message.reply_text(
            "*Оберіть сервіс:*",
            reply_markup=service_selection_markup(
                SERVICES
            ),  # Используем SERVICES из constants.py
            parse_mode="Markdown",
        )
        return SERVICE

    # CONFIRM_CREATE
    bot_vars = context.user_data.copy()

    # Формуємо опис для задачі
    description = (
        f"ПІБ: {bot_vars.get('full_name', '')}\n"
        f"Підрозділ: {bot_vars.get('division', '')}\n"
        f"Департамент: {bot_vars.get('department', '')}\n"
        f"Сервіс: {bot_vars.get('service', '')}\n"
        f"Опис: {bot_vars.get('description', '')}"
    )

    # Добавляем поле проекта и типа задачи, если они отсутствуют
    if "issuetype" not in bot_vars:
        bot_vars["issuetype"] = JIRA_ISSUE_TYPE  # Используем тип задачи из конфигурации

    # Изменяем ключ с project_key на project (в соответствии с fields_mapping.yaml)
    if "project" not in bot_vars:
        bot_vars["project"] = JIRA_PROJECT_KEY  # Используем код проекта из конфигурации

    # Добавляем summary и description
    bot_vars["summary"] = (
        f"{bot_vars.get('service', '')} - {bot_vars.get('description', '')[:50]}"
    )
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
        logger.info(
            f"Использую маппинг для division: {bot_vars['division']} -> {bot_vars[field_id]}"
        )

    if "department" in bot_vars and bot_vars["department"] in DEPARTMENT_ID_MAPPINGS:
        field_id = JIRA_FIELD_IDS["department"]
        bot_vars[field_id] = {
            "id": DEPARTMENT_ID_MAPPINGS[bot_vars["department"]]["id"]
        }
        logger.info(
            f"Использую маппинг для department: {bot_vars['department']} -> {bot_vars[field_id]}"
        )

    if "service" in bot_vars and bot_vars["service"] in SERVICE_ID_MAPPINGS:
        field_id = JIRA_FIELD_IDS["service"]
        bot_vars[field_id] = {"id": SERVICE_ID_MAPPINGS[bot_vars["service"]]["id"]}
        logger.info(
            f"Использую маппинг для service: {bot_vars['service']} -> {bot_vars[field_id]}"
        )

    payload = build_jira_payload(bot_vars)

    try:
        logger.info(f"Отправка запроса на создание задачі з полями: {payload}")
        logger.info(
            f"Використовуємо тип задачі: {bot_vars.get('issuetype')}, проект: {bot_vars.get('project')}"
        )

        # Переконаємось, що тип задачі та проект правильно вказані
        if "fields" in payload and "project" not in payload["fields"]:
            payload["fields"]["project"] = {
                "key": "SD"
            }  # Використовуємо дефолтний проект
            logger.info("Доданий дефолтний проект: SD")

        if "fields" in payload and "issuetype" not in payload["fields"]:
            payload["fields"]["issuetype"] = {
                "name": "Telegram"
            }  # Використовуємо дефолтний тип
            logger.info("Доданий дефолтний тип задачі: Telegram")

        # Додаємо перевірку на обов'язкові поля
        if "fields" in payload and "summary" not in payload["fields"]:
            context.user_data.pop("in_conversation", None)  # Очищаємо флаг
            await query.message.reply_text(
                "❌ *Помилка:* _відсутній заголовок задачі_",
                reply_markup=issues_view_markup,
                parse_mode="Markdown",
            )
            return ConversationHandler.END

        # Використовуємо правильно сформований payload
        issue_key = await create_jira_issue(payload)
        # Встановлюємо активну задачу
        context.user_data["active_task"] = issue_key

        # Оновлюємо стан користувача - тепер у нього є відкрита задача
        telegram_id = query.from_user.id
        set_user_current_task(telegram_id, issue_key)
        logger.info(
            f"🔄 Стан користувача {telegram_id} змінено на AUTHORIZED_WITH_TASK з задачею {issue_key}"
        )

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

                # ВИДАЛЕНО: Дублювання з webhook повідомленням про створення задачі
                # await query.message.reply_text(
                #     f"✅ Задача створена: *{issue_key}*\n"
                #     f"📸 Фото успішно прикріплено до задачі!\n"
                #     f"_Тепер ви можете додати коментар або прикріпити інші файли._",
                #     reply_markup=issues_view_markup,
                #     parse_mode="Markdown"
                # )
            except Exception as e:
                logger.error(
                    f"Помилка прикріплення фото до задачі {issue_key}: {str(e)}"
                )
                # ВИДАЛЕНО: Дублювання з webhook повідомленням про створення задачі
                # await query.message.reply_text(
                #     f"✅ Задача створена: *{issue_key}*\n"
                #     f"❌ Помилка прикріплення фото: _{str(e)}_\n"
                #     f"_Ви можете спробувати прикріпити фото знову через коментарі._",
                #     reply_markup=issues_view_markup,
                #     parse_mode="Markdown"
                # )
        else:
            # ЗАКОМЕНТОВАНО: Дублювання з webhook повідомленням
            # # Змінюємо клавіатуру на issues_view_markup для відображення кнопок оновлення статусу
            # await query.message.reply_text(f"✅ Задача створена: *{issue_key}*\n_Тепер ви можете додати коментар або прикріпити файл._",  # noqa: E501
            #                             reply_markup=issues_view_markup,
            #                             parse_mode="Markdown")
            pass  # Webhook вже надішле повідомлення про створення задачі

        # Очищаємо флаг conversation після успішного створення
        context.user_data.pop("in_conversation", None)

    except JiraApiError as e:
        error_message = str(e)
        # Извлекаем информативную часть сообщения об ошибке
        if "400" in error_message:
            if "field" in error_message.lower() and "required" in error_message.lower():
                error_message = "Відсутні обов'язкові поля в запиті. Будь ласка, заповніть всі необхідні поля."
            elif "issuetype" in error_message.lower():
                error_message = (
                    "Вказано невірний тип задачі. Будь ласка, виберіть правильний тип."
                )
            elif "project" in error_message.lower():
                error_message = (
                    "Вказано невірний проект. Будь ласка, виберіть правильний проект."
                )
            else:
                error_message = (
                    "Помилка у форматі запиту. Будь ласка, перевірте введені дані."
                )
        elif "401" in error_message or "403" in error_message:
            error_message = "Проблема з авторизацією в Jira. Будь ласка, зв'яжіться з адміністратором."
        elif "timeout" in error_message.lower():
            error_message = "Перевищено час очікування відповіді від Jira. Спробуйте ще раз пізніше."

        logger.error(f"Помилка при створенні задачі: {str(e)}")
        context.user_data.pop("in_conversation", None)  # Очищаємо флаг
        await query.message.reply_text(
            f"❌ *Помилка створення задачі:* _{error_message}_",
            reply_markup=issues_view_markup,
            parse_mode="Markdown",
        )
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Невідома помилка при створенні задачі: {str(e)}")
        context.user_data.pop("in_conversation", None)  # Очищаємо флаг
        await query.message.reply_text(
            "❌ *Помилка створення задачі.* _Будь ласка, спробуйте пізніше або зв'яжіться з адміністратором._",
            reply_markup=issues_view_markup,
            parse_mode="Markdown",
        )
        return ConversationHandler.END

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
                "account_id": context.user_data.get("account_id", ""),
            }

            if new_user_data["full_name"] and new_user_data["telegram_id"]:
                from src.google_sheets_service import add_new_user

                row_num = add_new_user(new_user_data)
                logger.info(
                    f"Новий користувач {new_user_data['full_name']} автоматично додано в Google Sheets: рядок {row_num}"
                )

                # Зберігаємо профіль користувача в контексті для майбутніх взаємодій
                context.user_data["profile"] = new_user_data
        except Exception as e:
            logger.error(
                f"Помилка автоматичного додавання нового користувача в Google Sheets: {e}"
            )

    # Очищаємо флаг активного conversation перед виходом
    context.user_data.pop("in_conversation", None)

    # Задачу створено успішно, виходимо з ConversationHandler
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скасувати ConversationHandler"""
    context.user_data.pop(
        "in_conversation", None
    )  # Очищаємо флаг активного conversation
    await update.message.reply_text(
        "❌ *Скасовано.*", reply_markup=issues_view_markup, parse_mode="Markdown"
    )
    return ConversationHandler.END


async def show_active_task_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показує детальну інформацію про активну задачу"""
    key = context.user_data.get("active_task")
    if not key:
        # Визначаємо, як відправити повідомлення
        if update.callback_query:
            await update.callback_query.message.reply_text(
                "❗ *Немає активної задачі для перегляду.*",
                reply_markup=issues_view_markup,
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                "❗ *Немає активної задачі для перегляду.*",
                reply_markup=issues_view_markup,
                parse_mode="Markdown",
            )
        return False

    try:
        # Отримуємо повні деталі задачі з Jira
        issue = await get_full_issue_info(key)

        # Логуємо отримані дані для діагностики проблеми з департаментом
        logger.info(
            f"Отримані дані задачі {key} від Jira API: department={issue.get('department')}, division={issue.get('division')}, service={issue.get('service')}"  # noqa: E501
        )

        # Используем модуль форматирования для единообразного отображения
        from src.fixed_issue_formatter import format_issue_info, format_issue_text

        # Получаем отформатированные данные
        formatted_issue = format_issue_info(issue)
        logger.info(
            f"Відформатовані дані задачі {key}: "
            f"department={formatted_issue.get('department')}, "
            f"division={formatted_issue.get('division')}, "
            f"service={formatted_issue.get('service')}"
        )

        # Формируем текст и добавляем защиту от разбивки на символы
        text = format_issue_text(formatted_issue)

        # Добавляем маркер невидимого пробела в начало текста, чтобы предотвратить разбиение на символы
        text = "\u200b" + text

        # Визначаємо, як відправити повідомлення
        if update.callback_query:
            await update.callback_query.message.reply_text(
                text,
                reply_markup=issues_view_markup,
                parse_mode=None,  # Отключаем парсинг Markdown/HTML для предотвращения проблем с форматированием
            )
        else:
            await update.message.reply_text(
                text,
                reply_markup=issues_view_markup,
                parse_mode=None,  # Отключаем парсинг Markdown/HTML для предотвращения проблем с форматированием
            )
        return True
    except Exception as e:
        logger.error(f"Помилка отримання деталей задачі {key}: {str(e)}")

        # Визначаємо, як відправити повідомлення про помилку
        if update.callback_query:
            await update.callback_query.message.reply_text(
                f"❌ Помилка отримання деталей задачі {key}: {str(e)}",
                reply_markup=issues_view_markup,
            )
        else:
            await update.message.reply_text(
                f"❌ Помилка отримання деталей задачі {key}: {str(e)}",
                reply_markup=issues_view_markup,
            )
        return False


async def sync_cache_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для синхронізації локального кешу з Google Sheets (тільки для адміністраторів)"""
    # Перевірка прав адміністратора (можна налаштувати список ID адміністраторів)
    admin_ids = [5667252017]  # Додайте ID адміністраторів
    user_id = update.effective_user.id

    if user_id not in admin_ids:
        await update.message.reply_text(
            "❌ *Доступ заборонено.*\n\nЦя команда доступна тільки адміністраторам.",
            parse_mode="Markdown",
        )
        return

    await update.message.reply_text(
        "🔄 *Починаємо синхронізацію...*", parse_mode="Markdown"
    )

    try:
        result = user_manager.sync_pending_users()

        sync_message = (
            f"✅ *Синхронізація завершена!*\n\n"
            f"📊 **Статистика:**\n"
            f"✅ Синхронізовано: {result['synced']}\n"
            f"❌ Помилок: {result['failed']}\n"
        )

        if result["errors"]:
            sync_message += "\n🔍 **Деталі помилок:**\n"
            for error in result["errors"][:5]:  # Показуємо тільки перші 5 помилок
                sync_message += f"• {error}\n"
            if len(result["errors"]) > 5:
                sync_message += f"...та ще {len(result['errors']) - 5} помилок"

        await update.message.reply_text(sync_message, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Помилка синхронізації: {e}")
        await update.message.reply_text(
            f"❌ *Помилка синхронізації:*\n{str(e)}", parse_mode="Markdown"
        )


async def cache_status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показує статус кешу для поточного користувача"""
    telegram_id = int(update.effective_user.id)

    try:
        cache_info = user_manager.get_user_cache_info(telegram_id)

        if cache_info.get("cached"):
            status_message = (
                f"💾 *Статус вашого кешу:*\n\n"
                f"✅ **В кеші:** Так\n"
                f"🔄 **Синхронізація:** {'✅ Синхронізовано' if cache_info.get('sync_status') else '⏳ Очікує'}\n"
                f"📅 **Остання синхронізація:** {cache_info.get('last_sync', 'Невідомо')}\n"
                f"🎯 **Статус:** {cache_info.get('status', 'Невідомо')}"
            )
        else:
            status_message = (
                "💾 *Статус вашого кешу:*\n\n"
                "❌ **В кеші:** Ні\n"
                "ℹ️ Ваші дані будуть кешовані після наступної авторизації."
            )

        await update.message.reply_text(status_message, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Помилка отримання статусу кешу: {e}")
        await update.message.reply_text(
            f"❌ *Помилка отримання статусу кешу:*\n{str(e)}", parse_mode="Markdown"
        )


async def reset_registration_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Скидання поточної реєстрації та повернення до головного меню"""
    telegram_id = int(update.effective_user.id)

    # Очищаємо всі дані реєстрації
    context.user_data.pop("registration", None)
    context.user_data.pop("registration_step", None)

    # Видаляємо файл стану
    from src.user_state_service import complete_registration

    complete_registration(telegram_id)

    await update.message.reply_text(
        "🔄 *Реєстрацію скинуто.*\n\n"
        "Ви повернулись до головного меню. Для реєстрації введіть команду /start",
        reply_markup=main_menu_markup,
        parse_mode="Markdown",
    )

    logger.info(f"Скинуто реєстрацію для користувача {telegram_id}")


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник для кнопки 'ℹ️ Допомога' - перенаправляє користувача до телеграм-каналу підтримки"""

    # Універсальна функція для роботи з message і callback_query
    async def send_message(text, reply_markup=None):
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(
                text, reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(text, reply_markup=reply_markup)

    await send_message(
        "Для отримання допомоги перейдіть до каналу підтримки: https://t.me/+zoabM0XuLeo2NzY6\n\n"
        "Там ви зможете поставити питання і отримати консультацію.",
        reply_markup=main_menu_markup,
    )


def register_handlers(application):
    """Реєстрація всіх хендлерів у Application"""

    # ConversationHandler для створення задачі
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.TEXT & filters.Regex("^🆕 Створити задачу$"), create_issue_start
            )
        ],
        states={
            FULL_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, full_name_handler)
            ],
            MOBILE_NUMBER: [
                MessageHandler(filters.CONTACT, contact_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, remind_to_use_button),
                # Відхиляємо всі типи медіа під час авторизації
                MessageHandler(
                    filters.PHOTO
                    | filters.VIDEO
                    | filters.Document.ALL
                    | filters.AUDIO
                    | filters.VOICE
                    | filters.Sticker.ALL
                    | filters.VIDEO_NOTE,
                    reject_any_action_during_auth,
                ),
            ],
            DIVISION: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND
                    & ~filters.Regex("^🏠 Вийти на головну$"),
                    division_handler,
                ),
                MessageHandler(
                    filters.Regex("^🏠 Вийти на головну$"),
                    return_to_main_from_conversation,
                ),
            ],
            DEPARTMENT: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND
                    & ~filters.Regex("^🏠 Вийти на головну$"),
                    department_handler,
                ),
                MessageHandler(
                    filters.Regex("^🏠 Вийти на головну$"),
                    return_to_main_from_conversation,
                ),
            ],
            SERVICE: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND
                    & ~filters.Regex("^(🏠 Вийти на головну|🔙 Назад)$"),
                    service_handler,
                ),
                MessageHandler(
                    filters.Regex("^🏠 Вийти на головну$"),
                    return_to_main_from_conversation,
                ),
                MessageHandler(
                    filters.Regex("^🔙 Назад$"), return_to_main_from_conversation
                ),
            ],
            DESCRIPTION: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND
                    & ~filters.Regex("^🏠 Вийти на головну$"),
                    description_handler,
                ),
                MessageHandler(filters.PHOTO, description_handler),
                MessageHandler(
                    filters.Regex("^🏠 Вийти на головну$"),
                    return_to_main_from_conversation,
                ),
            ],
            CONFIRM: [
                CallbackQueryHandler(
                    confirm_callback, pattern="^(CONFIRM_CREATE|BACK_TO_SERVICE)$"
                )
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)],
        per_message=False,  # Возвращаем обратно для совместимости с MessageHandler
        name="create_issue_conversation",
    )

    # ВАЖЛИВО: ConversationHandler має НАЙВИЩИЙ пріоритет (group=-1)
    # Це гарантує, що він обробить повідомлення РАНІШЕ за всі інші handlers
    application.add_handler(conv_handler, group=-1)

    # Глобальний обробник для кнопки "🔙 Назад" (group=0 - перед іншими)
    application.add_handler(
        MessageHandler(filters.Regex("^🔙 Назад$"), handle_back_button), group=0
    )

    # Команди - group 0 (після ConversationHandler, але перед іншими)
    application.add_handler(CommandHandler("start", start), group=0)
    application.add_handler(
        CommandHandler("reset", reset_registration_handler), group=0
    )
    application.add_handler(CommandHandler("sync_cache", sync_cache_handler), group=0)
    application.add_handler(
        CommandHandler("cache_status", cache_status_handler), group=0
    )

    # Кнопки головного меню - group 0
    # Примітка: кнопка "🆕 Створити задачу" обробляється ConversationHandler entry_point
    application.add_handler(
        MessageHandler(filters.Regex("🔄 Повторити /start"), restart_handler), group=0
    )
    application.add_handler(
        MessageHandler(filters.Regex("🔄 Повторна авторизація"), re_auth_handler),
        group=0,
    )
    application.add_handler(
        MessageHandler(filters.Regex("👤 Мій профіль"), my_profile_handler), group=0
    )
    application.add_handler(
        MessageHandler(filters.Regex("🧾 Мої задачі"), my_issues), group=0
    )
    application.add_handler(
        MessageHandler(filters.Regex("ℹ️ Допомога"), help_handler), group=0
    )
    application.add_handler(
        MessageHandler(filters.Regex("🏠 Вийти на головну"), return_to_main), group=0
    )
    application.add_handler(
        MessageHandler(filters.Regex("🔄 Оновити статус задачі"), update_issues_status),
        group=0,
    )
    application.add_handler(
        MessageHandler(filters.Regex("✅ Перевірити статус задачі"), check_status),
        group=0,
    )
    application.add_handler(
        MessageHandler(filters.Regex("💬 коментар до задачі"), comment_handler), group=0
    )

    # Глобальний contact_handler для початкової авторизації з головного меню
    application.add_handler(
        MessageHandler(filters.CONTACT, global_contact_handler), group=0
    )

    # File handler (ПЕРЕД global_awaiting_auth_media_handler для обробки медіа від авторизованих користувачів)
    application.add_handler(
        MessageHandler(
            filters.Document.ALL | filters.PHOTO | filters.VIDEO | filters.AUDIO,
            file_handler,
        ),
        group=0,
    )

    # 🔥 КРИТИЧНО: Глобальні handlers для неавторизованих користувачів (group=0)
    # Ці handlers спрацьовують ДО авторизації і блокують всі дії окрім надання номера
    application.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND
            & ~filters.Regex("^(🆕|🧾|🏠|ℹ️|💬|🔄|👤|✅)"),
            global_awaiting_auth_text_handler,
        ),
        group=0,
    )

    application.add_handler(
        MessageHandler(
            filters.PHOTO
            | filters.VIDEO
            | filters.Document.ALL
            | filters.AUDIO
            | filters.VOICE
            | filters.Sticker.ALL
            | filters.VIDEO_NOTE,
            global_awaiting_auth_media_handler,
        ),
        group=0,
    )

    # Callback handlers
    application.add_handler(
        CallbackQueryHandler(issue_callback, pattern="^ISSUE_"), group=0
    )

    # Обробник для збору опису після inline кнопок (вищий пріоритет, GROUP 0)
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND, handle_inline_issue_description
        ),
        group=0,
    )

    # Додаємо новий основний диспетчер з найвищим пріоритетом (GROUP 1)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, main_message_dispatcher),
        group=1,
    )

    # Глобальний обробник реєстрації нових користувачів (GROUP 2 - середній пріоритет)
    application.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND
            & ~filters.Regex("^(🆕 Створити задачу|🧾|🏠|ℹ️|💬 коментар до задачі)"),
            global_registration_handler,
        ),
        group=2,
    )

    # Обробник комментариев (GROUP 3 - нижчий пріоритет)
    application.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND
            & ~filters.Regex("^(🆕|🧾|✅|🏠|🔄|👤|❌|ℹ️|💬)"),
            comment_handler,
        ),
        group=3,
    )
