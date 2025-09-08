#!/bin/bash

echo "===== Bot Restart Script ====="
echo "$(date): Beginning restart process"

# Загружаем токен из файла credentials.env для безопасности
if [ -f "config/credentials.env" ]; then
    source config/credentials.env
    if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
        echo "ERROR: Failed to load TELEGRAM_BOT_TOKEN from config/credentials.env"
        exit 1
    fi
else
    echo "ERROR: config/credentials.env file not found"
    exit 1
fi

# Проверяем, не было ли перезапуска слишком недавно
# Создаем файл блокировки для контроля частых перезапусков
LOCKFILE="logs/restart.lock"
COOLDOWN_TIME=120  # минимальное время между перезапусками в секундах (увеличено до 2 минут)

if [ -f "$LOCKFILE" ]; then
    LAST_RESTART=$(cat "$LOCKFILE")
    NOW=$(date +%s)
    TIME_DIFF=$((NOW - LAST_RESTART))
    
    if [ $TIME_DIFF -lt $COOLDOWN_TIME ]; then
        WAIT_TIME=$((COOLDOWN_TIME - TIME_DIFF))
        echo "WARNING: Bot was restarted too recently (${TIME_DIFF} seconds ago)"
        echo "Waiting for ${WAIT_TIME} more seconds before continuing..."
        sleep $WAIT_TIME
    fi
fi

# Обновляем время последнего перезапуска
date +%s > "$LOCKFILE"

# Функция для очистки конфликтующих сессий Telegram API
clean_telegram_sessions() {
    echo "Cleaning up Telegram API sessions..."
    
    # Сначала пробуем удалить webhook, чтобы избежать конфликта с getUpdates
    echo "Deleting webhook and dropping pending updates..."
    RESPONSE=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/deleteWebhook?drop_pending_updates=true")
    echo "Webhook deletion response: $RESPONSE"
    
    # Проверка наличия конфликта через getMe
    echo "Checking API connection via getMe..."
    GETME_RESPONSE=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe")
    echo "getMe response: $GETME_RESPONSE"
    
    # Базовая проверка на ошибки в ответе
    if [[ "$GETME_RESPONSE" == *"\"ok\":false"* ]]; then
        echo "WARNING: API connection test failed"
        if [[ "$GETME_RESPONSE" == *"Conflict"* ]]; then
            echo "CRITICAL: Detected getUpdates conflict. Implementing exponential backoff..."
            for i in $(seq 1 5); do
                BACKOFF_TIME=$((2**i))
                echo "Attempt $i: Waiting for $BACKOFF_TIME seconds..."
                sleep $BACKOFF_TIME
                curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/deleteWebhook?drop_pending_updates=true" > /dev/null
                echo "Retry $i: Testing API connection again..."
                TEST_RESPONSE=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe")
                if [[ "$TEST_RESPONSE" == *"\"ok\":true"* ]]; then
                    echo "SUCCESS: API connection restored"
                    break
                fi
            done
        fi
    else
        echo "API connection verified successfully"
    fi
    
    sleep 3
}

# Выполняем очистку сессий Telegram API
clean_telegram_sessions

# Define state files
PID_FILE="logs/bot.pid"
LOCK_FILE="logs/bot.lock"
ERR_LOG="logs/conflict_errors.log"

# Clean up state files
clean_state_files() {
    echo "Cleaning up state files..."
    if [ -f "$PID_FILE" ]; then
        OLD_PID=$(cat "$PID_FILE")
        if ps -p "$OLD_PID" > /dev/null 2>&1; then
            echo "Stopping old bot process with PID $OLD_PID"
            kill "$OLD_PID" 2>/dev/null || kill -9 "$OLD_PID" 2>/dev/null
        else
            echo "Old PID file exists but process is not running"
        fi
        rm -f "$PID_FILE"
    fi
    
    # Remove lock file if it exists
    if [ -f "$LOCK_FILE" ]; then
        echo "Removing lock file"
        rm -f "$LOCK_FILE"
    fi
    
    # Log the cleanup to the conflict errors log
    echo "$(date): Cleaned up state files before restart" >> "$ERR_LOG"
}

# Run cleanup
clean_state_files

# Зупиняємо всі python-процеси, що запускали main.py
echo "Stopping all Python processes running main.py..."
pkill -f "python.*main.py" || echo "No Python processes found"
sleep 2

# Также останавливаем процессы Python, связанные с telegram
echo "Stopping any Python processes related to telegram..."
pkill -f "python.*telegram" || echo "No telegram processes found"
sleep 1

# Повторно і жорстко зупиняємо будь-які залишені процеси
echo "Ensuring all processes are stopped..."
pkill -9 -f "python.*main.py" || echo "No main.py processes needed to be force-killed"
pkill -9 -f "python.*telegram" || echo "No telegram processes needed to be force-killed"
sleep 2

# Проверяем наличие всех процессов Python, которые могут быть связаны с ботом
echo "Checking for any remaining Python processes..."
ps aux | grep -E "python.*main.py|python.*telegram" | grep -v grep

# Перевіряємо, що всі процеси точно зупинені
remaining=$(ps aux | grep -E "python.*main.py|python.*telegram" | grep -v grep)
if [ ! -z "$remaining" ]; then
    echo "WARNING: Some bot processes might still be running. Attempting stronger kill..."
    kill_procs=$(ps aux | grep -E "python.*main.py|python.*telegram" | grep -v grep | awk '{print $2}')
    for pid in $kill_procs; do
        echo "Force killing PID $pid..."
        kill -9 $pid 2>/dev/null || echo "Could not kill PID $pid"
    done
    sleep 2
    
    # Повторная проверка
    still_remaining=$(ps aux | grep -E "python.*main.py|python.*telegram" | grep -v grep)
    if [ ! -z "$still_remaining" ]; then
        echo "ERROR: Failed to kill all bot processes. Manual intervention required."
        echo "Remaining processes:"
        echo "$still_remaining"
        # Продолжаем выполнение скрипта, но выводим предупреждение
        echo "Will attempt to continue anyway..."
    else
        echo "All bot processes successfully terminated."
    fi
else
    echo "All bot processes successfully terminated."
fi

# Видаляємо lock-файл і всі інші файли стану, которые могут вызвать конфликты
echo "Removing lock and state files..."

# Список файлов, которые нужно удалить
# Bot-related locks
rm -f logs/bot.lock logs/telegram_bot.lock logs/bot_instance.lock

# Telegram API session files
rm -f *.session
rm -f *.session-journal

# Temporary and state files
rm -f *.tmp
rm -f *.state
rm -f *.cache
rm -f telegram_*.json

# Очищение подкаталога .telegram-bot-api если он существует
if [ -d ".telegram-bot-api" ]; then
    echo "Cleaning .telegram-bot-api directory..."
    rm -rf .telegram-bot-api/*
fi

# Проверьте наличие директории .telegrambot и очистите ее
if [ -d ".telegrambot" ]; then
    echo "Cleaning .telegrambot directory..."
    rm -rf .telegrambot/*
fi

# Очищення кэша Python для предотвращения проблем с импортом модулей
find . -name "*.pyc" -delete
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# Check for and clean specific Telegram-related cache directories
for dir in "$HOME/.cache/telegram" "$HOME/.local/share/TelegramDesktop" "$HOME/.telegram-cli"; do
    if [ -d "$dir" ]; then
        echo "Cleaning Telegram cache directory: $dir"
        find "$dir" -name "*.tmp" -delete 2>/dev/null || true
    fi
done

echo "State files and Python cache cleaned up."

# Додатково очищаємо з'єднання з Telegram API
echo "Resetting connection to Telegram API..."

# Удаляем webhook и сбрасываем ожидающие обновления
# TELEGRAM_BOT_TOKEN уже загружен из credentials.env
for i in {1..3}; do
    echo "Attempt $i: Deleting webhook and dropping updates..."
    curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/deleteWebhook?drop_pending_updates=true" > /dev/null
    sleep 3
done
echo "Webhook deleted and pending updates dropped"

# Затем делаем несколько запросов getUpdates для сброса соединения
for i in {1..3}; do
    echo "Attempt $i: Resetting getUpdates connection..."
    curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getUpdates?offset=-1&timeout=1" > /dev/null
    sleep 3
done
echo "getUpdates connection reset"

# Проверяем, нет ли активных сессий getUpdates с экспоненциальным ожиданием при конфликтах
MAX_ATTEMPTS=5
for attempt in $(seq 1 $MAX_ATTEMPTS); do
    echo "Checking for active getUpdates sessions (attempt $attempt/$MAX_ATTEMPTS)..."
    SESSIONS_CHECK=$(curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getUpdates?limit=1&timeout=1" 2>&1)
    
    if echo "$SESSIONS_CHECK" | grep -q "Conflict: terminated"; then
        # Экспоненциальный backoff: 5, 10, 20, 40, 80 секунд
        WAIT_TIME=$((5 * 2**(attempt-1)))
        echo "WARNING: Detected conflict with getUpdates. Waiting $WAIT_TIME seconds..."
        
        # Сначала сбрасываем webhook
        curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/deleteWebhook?drop_pending_updates=true" > /dev/null
        sleep 2
        
        # Затем делаем попытку очистить сессию getUpdates
        echo "Resetting getUpdates session (attempt $attempt)..."
        curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getUpdates?offset=-1&timeout=1" > /dev/null
        
        # Ждем с экспоненциальным backoff
        sleep $WAIT_TIME
        
        # Если это последняя попытка, выдаём особое предупреждение
        if [ $attempt -eq $MAX_ATTEMPTS ]; then
            echo "WARNING: Maximum retry attempts reached for resolving getUpdates conflict."
            echo "Bot may still experience 'Conflict: terminated' errors."
            echo "Consider manually restarting the machine if conflicts persist."
        fi
    else
        echo "No active conflicting getUpdates sessions detected on attempt $attempt."
        break
    fi
done

sleep 5

# Перед запуском сделаем еще одну проверку для уверенности
echo "Final check for any bot processes before starting new instance..."
sleep 2
remaining=$(ps aux | grep -E "python.*main.py|python.*telegram" | grep -v grep)
if [ ! -z "$remaining" ]; then
    echo "WARNING: Some processes are still running. Will continue anyway but conflicts may occur."
fi

# Запускаємо новий процес у фоновому режимі з перенаправленням логів
echo "Starting new bot instance in background..."
cd "$(dirname "$0")/.."  # Go to project root directory

# Добавляем специальный флаг для обнаружения конфликтов при запуске
mkdir -p logs
echo "# Bot startup: $(date)" > logs/bot_new.log
echo "export TELEGRAM_BOT_RESTART_TIME=$(date +%s)" >> logs/bot_new.log

# Запуск бота с дополнительными параметрами для обнаружения проблем
cd /home/Bot1 && source venv/bin/activate && export PYTHONPATH=/home/Bot1:$PYTHONPATH && nohup python src/main.py > logs/bot_new.log 2>&1 &
BOT_PID=$!
echo "Started bot with PID: $BOT_PID"

# Записываем PID в файл для удобства завершения в будущем
echo "$BOT_PID" > logs/bot.pid

# Перевіряємо, чи успішно запустився через 20 секунд - увеличили время ожидания
echo "Waiting for bot to initialize (20 seconds)..."
sleep 20

if ps -p $BOT_PID > /dev/null; then
    echo "Bot process is running with PID: $BOT_PID ($(date))"
    echo "Log output is being written to logs/bot_new.log"
    
    # Проверим, работает ли бот полноценно, отправив тестовый запрос к API
    echo "Verifying bot can connect to Telegram API..."
    API_CHECK=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe" 2>&1)
    
    if echo "$API_CHECK" | grep -q '"ok":true'; then
        echo "✓ Bot successfully connected to Telegram API!"
        
        # Запишем время успешного запуска для отладки
        echo "$(date): Bot successfully restarted and connected to API" >> logs/bot_restart_history.log
    else
        echo "✗ WARNING: Bot is running, but API connection check failed!"
        echo "API response: $API_CHECK"
        echo "$(date): Bot restarted but API connection check failed" >> logs/bot_restart_history.log
    fi
    
    # Перевіряємо, чи немає помилок в логах
    if grep -q "ERROR\|error\|Exception\|exception\|Conflict" logs/bot_new.log; then
        echo "WARNING: Errors detected in log file:"
        grep -E "ERROR|error|Exception|exception|Conflict" logs/bot_new.log | tail -10
        echo "Check logs/bot_new.log for full error details."
        
        # Специально проверяем на наличие Conflict ошибок и сохраняем статистику
        if grep -q "Conflict: terminated by other getUpdates request" logs/bot_new.log; then
            echo "ERROR: Detected getUpdates conflict! Bot may not function correctly."
            echo "$(date): getUpdates conflict detected after restart" >> conflict_errors.log
            CONFLICT_COUNT=$(grep -c "Conflict: terminated" conflict_errors.log)
            echo "Total conflicts detected (historical): $CONFLICT_COUNT"
            
            # Рекомендации по устранению частых конфликтов
            if [ $CONFLICT_COUNT -gt 5 ]; then
                echo "RECOMMENDATION: You're experiencing frequent getUpdates conflicts."
                echo "Consider the following solutions:"
                echo "1. Increase COOLDOWN_TIME to at least 300 seconds (5 minutes)"
                echo "2. Restart the server machine completely"
                echo "3. Check for any other Telegram bots running on the same machine"
                echo "4. Verify network connectivity and firewall settings"
            fi
        fi
        
        # Смотрим, есть ли другие ошибки кроме конфликтов
        if grep -q -v "Conflict: terminated" logs/bot_new.log | grep -q "ERROR\|error\|Exception\|exception"; then
            echo "OTHER ERRORS detected in logs:"
            grep -v "Conflict: terminated" logs/bot_new.log | grep -E "ERROR|error|Exception|exception" | tail -5
        fi
    else
        echo "✓ No immediate errors detected in logs."
    fi
    
    echo "------------------------------"
    echo "Bot is now running. To view logs in real-time, use: tail -f logs/bot_new.log"
    echo "To stop the bot, use: kill $(cat logs/bot.pid)"
    echo "------------------------------"
else
    echo "ERROR: Bot process terminated unexpectedly! Check logs/bot_new.log for details."
    echo "Last 15 lines of log:"
    tail -15 logs/bot_new.log
    echo "$(date): Bot failed to start - process terminated" >> logs/bot_restart_history.log
    exit 1
fi

# Функция для диагностики конфликтов getUpdates и предложения решений
diagnose_conflicts() {
    echo "===== Telegram Bot Conflict Diagnostics ====="
    echo "Running diagnostics to help resolve persistent getUpdates conflicts"
    
    # Проверяем логи на наличие конфликтов
    CONFLICT_COUNT=$(grep -c "Conflict: terminated" logs/bot_new.log 2>/dev/null || echo "0")
    echo "Number of conflicts in current log: $CONFLICT_COUNT"
    
    # Проверяем, есть ли другие процессы python, использующие телеграм
    PYTHON_PROCS=$(ps aux | grep -E "python.*telegram" | grep -v grep | wc -l)
    echo "Number of Python processes related to Telegram: $PYTHON_PROCS"
    
    # Проверяем сетевые соединения с telegram
    echo "Active network connections to api.telegram.org:"
    netstat -an | grep "telegram" | head -5
    
    # Проверяем наличие локальных файлов сессий
    SESSION_FILES=$(find . -name "*.session*" | wc -l)
    echo "Telegram session files found: $SESSION_FILES"
    
    echo ""
    echo "RECOMMENDATIONS:"
    echo "1. If conflicts persist, increase COOLDOWN_TIME to 300 (5 minutes)"
    echo "2. Consider adding 'asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())' to your bot code"
    echo "3. Make sure you don't have multiple bot instances running"
    echo "4. Check for network connectivity issues or API rate limiting"
    echo "5. As a last resort, reboot the server"
    echo "===== End of Diagnostics ====="
}

# Запускаем диагностику, если обнаружены конфликты
if grep -q "Conflict: terminated" logs/bot_new.log 2>/dev/null; then
    diagnose_conflicts
fi

echo "===== Restart Complete ====="
