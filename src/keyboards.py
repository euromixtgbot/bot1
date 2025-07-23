# keyboards.py

from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from src.constants import DIVISIONS, DEPARTMENTS, SERVICES

# Кнопки головного меню
MAIN_MENU_BUTTONS = [
    ["🧾 Мої задачі", "🆕 Створити задачу"],
    ["ℹ️ Допомога", "🔄 Повторити /start"]
]
main_menu_markup = ReplyKeyboardMarkup(
    MAIN_MENU_BUTTONS,
    resize_keyboard=True,
    one_time_keyboard=False
)

# Кнопка для запиту контактів
contact_request_markup = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📞 Надати номер телефону", request_contact=True)]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

# Кнопка для запиту контактів при неуспішній авторизації
failed_auth_markup = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📞 Надати номер телефону", request_contact=True)],
        [KeyboardButton("👤 Продовжити без авторизації")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

# Кнопки після створення задачі
AFTER_CREATE_BUTTONS = [
    ["✅ Перевірити статус задачі"],

]
after_create_markup = ReplyKeyboardMarkup(
    AFTER_CREATE_BUTTONS,
    resize_keyboard=True,
    one_time_keyboard=False
)

# Кнопки для режиму перегляду задач
ISSUES_VIEW_BUTTONS = [
    ["🔄 Оновити статус задачі"],
    ["🏠 Вийти на головну"]
]
issues_view_markup = ReplyKeyboardMarkup(
    ISSUES_VIEW_BUTTONS,
    resize_keyboard=True,
    one_time_keyboard=False
)

# Кнопки для кроку «Сервіс»
def service_selection_markup(services: list) -> ReplyKeyboardMarkup:
    """
    services: список рядків з назвами сервісів
    """
    # Розбиваємо на ряди по 2 кнопки
    buttons = [services[i : i + 2] for i in range(0, len(services), 2)]
    # Додаємо кнопку Назад у кінець
    buttons.append(["🔙 Назад"])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)

# Inline-кнопки у діалозі підтвердження
confirm_issue_markup = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("Створити задачу", callback_data="CONFIRM_CREATE"),
        InlineKeyboardButton("🔙 Назад", callback_data="BACK_TO_SERVICE")
    ]
])

# Функція для генерації списку моїх задач - більше не використовується для інлайн-кнопок
def my_issues_markup(issues: list) -> InlineKeyboardMarkup:
    """
    Ця функція збережена для сумісності, але більше не використовується для створення
    інлайн-кнопок. Список задач тепер відображається як текст.
    """
    buttons = [
        [InlineKeyboardButton(f"{item['key']} — {item['status']}", callback_data=f"ISSUE_{item['key']}")]
        for item in issues
    ]
    return InlineKeyboardMarkup(buttons)