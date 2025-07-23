#!/bin/bash

# Автоматичне встановлення systemd service для Telegram бота

BOT_DIR="/home/Bot1"
SERVICE_NAME="telegram-bot"
SERVICE_FILE="$BOT_DIR/$SERVICE_NAME.service"
SYSTEMD_DIR="/etc/systemd/system"
MONITOR_SCRIPT="$BOT_DIR/bot_monitor.sh"

echo "=== Встановлення автозапуску Telegram бота ==="

# Перевіряємо чи скрипт запущено з правами root
if [ "$EUID" -ne 0 ]; then
    echo "ПОМИЛКА: Цей скрипт потрібно запускати з правами root (sudo)"
    exit 1
fi

# Перевіряємо чи існують необхідні файли
if [ ! -f "$SERVICE_FILE" ]; then
    echo "ПОМИЛКА: Файл service не знайдено: $SERVICE_FILE"
    exit 1
fi

if [ ! -f "$MONITOR_SCRIPT" ]; then
    echo "ПОМИЛКА: Скрипт моніторингу не знайдено: $MONITOR_SCRIPT"
    exit 1
fi

# Зупиняємо існуючий сервіс якщо він працює
echo "Зупиняємо існуючий сервіс (якщо працює)..."
systemctl stop "$SERVICE_NAME" 2>/dev/null || true
systemctl disable "$SERVICE_NAME" 2>/dev/null || true

# Копіюємо service файл до systemd
echo "Копіюємо service файл до systemd..."
cp "$SERVICE_FILE" "$SYSTEMD_DIR/"

# Перезавантажуємо systemd
echo "Перезавантажуємо systemd daemon..."
systemctl daemon-reload

# Включаємо автозапуск
echo "Включаємо автозапуск сервісу..."
systemctl enable "$SERVICE_NAME"

# Запускаємо сервіс
echo "Запускаємо сервіс..."
systemctl start "$SERVICE_NAME"

# Перевіряємо статус
sleep 3
if systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "✅ Сервіс успішно запущено!"
    systemctl status "$SERVICE_NAME" --no-pager -l
else
    echo "❌ Помилка запуску сервісу!"
    systemctl status "$SERVICE_NAME" --no-pager -l
    echo ""
    echo "Останні логи:"
    journalctl -u "$SERVICE_NAME" --no-pager -n 20
    exit 1
fi

# Додаємо cron job для моніторингу (кожні 2 хвилини)
echo ""
echo "Налаштовуємо cron для додаткового моніторингу..."

# Створюємо новий crontab entry
CRON_JOB="*/2 * * * * $MONITOR_SCRIPT monitor >/dev/null 2>&1"

# Перевіряємо чи cron job вже існує
if crontab -l 2>/dev/null | grep -q "$MONITOR_SCRIPT"; then
    echo "Cron job вже існує, оновлюємо..."
    # Видаляємо старий і додаємо новий
    (crontab -l 2>/dev/null | grep -v "$MONITOR_SCRIPT"; echo "$CRON_JOB") | crontab -
else
    echo "Додаємо новий cron job..."
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
fi

echo ""
echo "=== Встановлення завершено ==="
echo ""
echo "Корисні команди для управління ботом:"
echo "  sudo systemctl start $SERVICE_NAME    # Запустити"
echo "  sudo systemctl stop $SERVICE_NAME     # Зупинити"
echo "  sudo systemctl restart $SERVICE_NAME  # Перезапустити"
echo "  sudo systemctl status $SERVICE_NAME   # Статус"
echo "  sudo journalctl -u $SERVICE_NAME -f   # Логи в реальному часі"
echo ""
echo "  $MONITOR_SCRIPT status                # Перевірити здоров'я"
echo "  $MONITOR_SCRIPT restart               # Ручний перезапуск"
echo ""
echo "Автоматичний моніторинг:"
echo "  - Systemd автоматично перезапускає при збоях"
echo "  - Cron перевіряє здоров'я кожні 2 хвилини"
echo "  - Логи моніторингу: $BOT_DIR/logs/monitor.log"
echo ""
echo "При перезавантаженні сервера бот запуститься автоматично."
