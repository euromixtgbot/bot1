#!/bin/bash

# Скрипт для тестування автозапуску бота

echo "=== Тестування автозапуску Telegram бота ==="
echo ""

# Функція виводу статусу
show_status() {
    echo "Поточний статус:"
    echo "  Systemd service: $(systemctl is-active telegram-bot)"
    echo "  Health check: $(cd /home/Bot1 && ./bot_monitor.sh status >/dev/null 2>&1 && echo "OK" || echo "FAILED")"
    echo "  Webhook endpoint: $(curl -s http://localhost:9443/rest/webhooks/ping >/dev/null 2>&1 && echo "OK" || echo "FAILED")"
    echo ""
}

echo "1. Початковий стан:"
show_status

echo "2. Тестуємо 'аварійну' зупинку процесу (kill -9)..."
BOT_PID=$(systemctl show telegram-bot --property=MainPID --value)
if [ "$BOT_PID" != "0" ] && [ -n "$BOT_PID" ]; then
    echo "Вбиваємо процес $BOT_PID..."
    sudo kill -9 "$BOT_PID"
    echo "Чекаємо 15 секунд для автоматичного перезапуску..."
    sleep 15
    show_status
else
    echo "Не вдалося знайти PID процесу"
fi

echo "3. Тестуємо зупинку сервісу:"
sudo systemctl stop telegram-bot
echo "Сервіс зупинено. Статус:"
show_status

echo "4. Тестуємо запуск сервісу:"
sudo systemctl start telegram-bot
sleep 5
echo "Сервіс запущено. Статус:"
show_status

echo "5. Тестуємо cron моніторинг (запускаємо вручну):"
cd /home/Bot1 && ./bot_monitor.sh monitor
echo "Моніторинг виконано. Статус:"
show_status

echo "6. Перевіряємо налаштування автозапуску:"
echo "  Autostart enabled: $(systemctl is-enabled telegram-bot)"
echo "  Cron job: $(crontab -l 2>/dev/null | grep -c bot_monitor.sh) записів знайдено"

echo ""
echo "=== Тестування завершено ==="
echo ""
echo "Корисні команди для моніторингу:"
echo "  sudo systemctl status telegram-bot     # Статус сервісу"
echo "  sudo journalctl -u telegram-bot -f     # Логи systemd в реальному часі"
echo "  cd /home/Bot1 && ./bot_control.sh logs # Логи бота"
echo "  tail -f /home/Bot1/logs/monitor.log    # Логи моніторингу"
