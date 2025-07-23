#!/bin/bash

# Швидкий скрипт для управління ботом без systemd

BOT_DIR="/home/Bot1"
MONITOR_SCRIPT="$BOT_DIR/bot_monitor.sh"

case "${1:-status}" in
    start)
        echo "Запускаю бота..."
        "$MONITOR_SCRIPT" start
        ;;
    stop)
        echo "Зупиняю бота..."
        "$MONITOR_SCRIPT" stop
        ;;
    restart)
        echo "Перезапускаю бота..."
        "$MONITOR_SCRIPT" restart
        ;;
    status)
        echo "Перевіряю статус бота..."
        "$MONITOR_SCRIPT" status
        ;;
    logs)
        echo "Показую останні логи бота:"
        tail -50 "$BOT_DIR/logs/bot.log"
        ;;
    monitor-logs)
        echo "Показую логи моніторингу:"
        tail -50 "$BOT_DIR/logs/monitor.log" 2>/dev/null || echo "Логи моніторингу поки що відсутні"
        ;;
    follow-logs)
        echo "Відслідковую логи в реальному часі (Ctrl+C для виходу):"
        tail -f "$BOT_DIR/logs/bot.log"
        ;;
    *)
        echo "Управління Telegram ботом"
        echo ""
        echo "Використання: $0 [команда]"
        echo ""
        echo "Команди:"
        echo "  start          Запустити бота"
        echo "  stop           Зупинити бота"
        echo "  restart        Перезапустити бота"
        echo "  status         Показати статус (за замовчуванням)"
        echo "  logs           Показати останні логи"
        echo "  monitor-logs   Показати логи моніторингу"
        echo "  follow-logs    Відслідковувати логи в реальному часі"
        echo ""
        echo "Поточний статус:"
        "$MONITOR_SCRIPT" status
        ;;
esac
