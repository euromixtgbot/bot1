#!/bin/bash

# Bot Health Monitor Script
# Monitors the bot process and restarts it if needed

BOT_DIR="/home/Bot1"
LOG_FILE="$BOT_DIR/logs/monitor.log"
PYTHON_PATH="$BOT_DIR/venv/bin/python"
BOT_SCRIPT="$BOT_DIR/src/main.py"
PID_FILE="$BOT_DIR/logs/bot.pid"
LOCK_FILE="$BOT_DIR/logs/bot.lock"

# Максимальний розмір лог файлу в байтах (5MB)
MAX_LOG_SIZE=5242880

# Створюємо директорію для логів якщо не існує
mkdir -p "$BOT_DIR/logs"

# Функція ротації логів
rotate_log_if_needed() {
    if [ -f "$LOG_FILE" ] && [ $(stat -c%s "$LOG_FILE") -gt $MAX_LOG_SIZE ]; then
        local timestamp=$(date '+%Y%m%d_%H%M%S')
        local counter=1
        local new_log_name="$BOT_DIR/logs/monitor_$(printf '%03d' $counter)_${timestamp}.log"
        
        # Знаходимо наступний доступний номер файлу
        while [ -f "$new_log_name" ]; do
            counter=$((counter + 1))
            new_log_name="$BOT_DIR/logs/monitor_$(printf '%03d' $counter)_${timestamp}.log"
        done
        
        # Переміщуємо старий лог файл
        mv "$LOG_FILE" "$new_log_name"
        
        # Видаляємо старі лог файли, залишаємо тільки останні 10
        find "$BOT_DIR/logs" -name "monitor_*.log" -type f | sort | head -n -10 | xargs -r rm
        
        echo "$(date '+%Y-%m-%d %H:%M:%S') - Log rotated: created $new_log_name" >> "$LOG_FILE"
    fi
}

# Функція логування з перевіркою ротації
log_message() {
    rotate_log_if_needed
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

# Функція перевірки здоров'я бота
check_bot_health() {
    # Перевіряємо через systemd якщо він доступний
    if command -v systemctl >/dev/null 2>&1; then
        if systemctl is-active --quiet telegram-bot 2>/dev/null; then
            # Systemd каже що сервіс активний, перевіряємо webhook
            local health_check=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:9443/rest/webhooks/ping --max-time 10)
            if [ "$health_check" = "200" ]; then
                return 0  # Бот здоровий
            else
                log_message "WARNING: Systemd service active but webhook server not responding (HTTP $health_check)"
                return 1  # Webhook сервер не відповідає
            fi
        else
            return 1  # Systemd сервіс не активний
        fi
    else
        # Fallback до PID файлу якщо systemd недоступний
        if [ -f "$PID_FILE" ]; then
            local pid=$(cat "$PID_FILE")
            if ps -p "$pid" > /dev/null 2>&1; then
                # Процес працює, перевіряємо чи відповідає на запити
                local health_check=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:9443/rest/webhooks/ping --max-time 10)
                if [ "$health_check" = "200" ]; then
                    return 0  # Бот здоровий
                else
                    log_message "WARNING: Bot process exists but webhook server not responding (HTTP $health_check)"
                    return 1  # Webhook сервер не відповідає
                fi
            else
                log_message "WARNING: PID file exists but process not running"
                rm -f "$PID_FILE"
                return 1  # Процес не працює
            fi
        else
            return 1  # PID файл не існує
        fi
    fi
}

# Функція запуску бота
start_bot() {
    log_message "Starting bot..."
    
    # Якщо доступний systemd, використовуємо його
    if command -v systemctl >/dev/null 2>&1; then
        systemctl start telegram-bot
        sleep 5
        
        if check_bot_health; then
            log_message "Bot started successfully via systemd"
            return 0
        else
            log_message "ERROR: Bot failed to start via systemd"
            return 1
        fi
    else
        # Fallback до ручного запуску
        # Очищаємо старі файли
        rm -f "$PID_FILE" "$LOCK_FILE"
        
        # Переходимо в директорію бота
        cd "$BOT_DIR" || {
            log_message "ERROR: Cannot change to bot directory"
            return 1
        }
        
        # Активуємо віртуальне середовище і запускаємо бота
        source venv/bin/activate
        nohup "$PYTHON_PATH" "$BOT_SCRIPT" >> "$BOT_DIR/logs/bot.log" 2>&1 &
        local new_pid=$!
        
        # Зберігаємо PID
        echo "$new_pid" > "$PID_FILE"
        
        # Чекаємо запуску
        sleep 5
        
        if check_bot_health; then
            log_message "Bot started successfully (PID: $new_pid)"
            return 0
        else
            log_message "ERROR: Bot failed to start properly"
            return 1
        fi
    fi
}

# Функція зупинки бота
stop_bot() {
    log_message "Stopping bot..."
    
    # Якщо доступний systemd, використовуємо його
    if command -v systemctl >/dev/null 2>&1; then
        systemctl stop telegram-bot
        sleep 3
        log_message "Bot stopped via systemd"
    else
        # Fallback до ручної зупинки
        if [ -f "$PID_FILE" ]; then
            local pid=$(cat "$PID_FILE")
            if ps -p "$pid" > /dev/null 2>&1; then
                kill -TERM "$pid"
                sleep 5
                
                # Якщо процес все ще працює, використовуємо KILL
                if ps -p "$pid" > /dev/null 2>&1; then
                    kill -KILL "$pid"
                    sleep 2
                fi
            fi
            rm -f "$PID_FILE"
        fi
        
        # Додатково вбиваємо всі процеси main.py
        pkill -f "python.*main.py" 2>/dev/null || true
        
        rm -f "$LOCK_FILE"
        log_message "Bot stopped"
    fi
}

# Функція перезапуску
restart_bot() {
    log_message "Restarting bot due to health check failure"
    
    # Якщо доступний systemd, використовуємо його
    if command -v systemctl >/dev/null 2>&1; then
        systemctl restart telegram-bot
        sleep 5
        log_message "Bot restarted via systemd"
    else
        # Fallback до ручного перезапуску
        stop_bot
        sleep 3
        start_bot
    fi
}

# Основна логіка
case "${1:-monitor}" in
    start)
        log_message "=== Manual bot start requested ==="
        start_bot
        ;;
    stop)
        log_message "=== Manual bot stop requested ==="
        stop_bot
        ;;
    restart)
        log_message "=== Manual bot restart requested ==="
        restart_bot
        ;;
    status)
        if check_bot_health; then
            echo "Bot is running and healthy"
            exit 0
        else
            echo "Bot is not running or unhealthy"
            exit 1
        fi
        ;;
    monitor)
        # Перевіряємо здоров'я бота
        if ! check_bot_health; then
            log_message "Bot health check failed, attempting restart"
            restart_bot
            
            # Перевіряємо чи вдалося перезапустити
            sleep 10
            if ! check_bot_health; then
                log_message "ERROR: Failed to restart bot after health check failure"
                exit 1
            fi
        fi
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|monitor}"
        echo "  start   - Start the bot"
        echo "  stop    - Stop the bot"
        echo "  restart - Restart the bot"
        echo "  status  - Check bot status"
        echo "  monitor - Check health and restart if needed (default)"
        exit 1
        ;;
esac
