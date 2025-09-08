#!/bin/bash

# =====================================
# BOT MONITORING AND AUTO-RESTART SCRIPT
# =====================================
# Цей скрипт моніторить роботу Telegram бота та автоматично перезапускає його при потребі
# Перевіряє стан бота кожні 15 хвилин
# При проблемах спочатку перезапускає бот, потім сервер якщо потрібно

# Конфігурація
BOT_DIR="/home/Bot1"
BOT_SCRIPT="src/main.py"
VENV_PATH="$BOT_DIR/venv"
ACTIVATE_SCRIPT="$BOT_DIR/activate_and_run.sh"
LOG_FILE="$BOT_DIR/logs/monitor.log"
PID_FILE="$BOT_DIR/bot.pid"
MAX_RESTART_ATTEMPTS=3
RESTART_COOLDOWN=60  # секунди між спробами
SERVER_RESTART_DELAY=120  # секунди після перезапуску сервера
CHECK_INTERVAL=900  # 15 хвилин в секундах

# Кольори для виводу
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функція логування
log() {
    local level=$1
    shift
    local message="$@"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "[$timestamp] [$level] $message" | tee -a "$LOG_FILE"
}

# Функція для перевірки чи працює бот
is_bot_running() {
    # Перевіряємо по PID файлу
    if [[ -f "$PID_FILE" ]]; then
        local pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            # Перевіряємо чи це дійсно наш бот
            if ps -p "$pid" -o cmd --no-headers | grep -q "python.*main.py"; then
                return 0  # Бот працює
            fi
        fi
        # PID файл існує, але процес не знайдений - видаляємо файл
        rm -f "$PID_FILE"
    fi
    
    # Альтернативна перевірка по назві процесу
    if pgrep -f "python.*$BOT_SCRIPT" > /dev/null; then
        return 0  # Бот працює
    fi
    
    return 1  # Бот не працює
}

# Функція для зупинки бота
stop_bot() {
    log "INFO" "🛑 Зупинка бота..."
    
    # Зупинка по PID файлу
    if [[ -f "$PID_FILE" ]]; then
        local pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            kill "$pid" 2>/dev/null
            sleep 3
            
            # Якщо процес все ще працює, примусова зупинка
            if ps -p "$pid" > /dev/null 2>&1; then
                kill -9 "$pid" 2>/dev/null
                sleep 2
            fi
        fi
        rm -f "$PID_FILE"
    fi
    
    # Зупинка всіх процесів бота
    pkill -f "python.*$BOT_SCRIPT" 2>/dev/null
    sleep 2
    
    # Примусова зупинка якщо потрібно
    pkill -9 -f "python.*$BOT_SCRIPT" 2>/dev/null
    
    log "INFO" "✅ Бот зупинено"
}

# Функція для запуску бота
start_bot() {
    log "INFO" "🚀 Запуск бота..."
    
    cd "$BOT_DIR" || {
        log "ERROR" "❌ Не вдається перейти до директорії $BOT_DIR"
        return 1
    }
    
    # Перевіряємо наявність віртуального середовища
    if [[ ! -d "$VENV_PATH" ]]; then
        log "ERROR" "❌ Віртуальне середовище не знайдено: $VENV_PATH"
        return 1
    fi
    
    # Перевіряємо наявність скрипта активації
    if [[ ! -f "$ACTIVATE_SCRIPT" ]]; then
        log "ERROR" "❌ Скрипт активації не знайдено: $ACTIVATE_SCRIPT"
        return 1
    fi
    
    # Перевіряємо наявність основного скрипта бота
    if [[ ! -f "$BOT_SCRIPT" ]]; then
        log "ERROR" "❌ Файл $BOT_SCRIPT не знайдено"
        return 1
    fi
    
    # Запускаємо бота через віртуальне середовище в фоні
    nohup bash -c "
        cd '$BOT_DIR'
        source '$VENV_PATH/bin/activate'
        export PYTHONPATH='$BOT_DIR:\$PYTHONPATH'
        python '$BOT_SCRIPT'
    " > /dev/null 2>&1 &
    
    local bot_pid=$!
    
    # Зберігаємо PID
    echo "$bot_pid" > "$PID_FILE"
    
    # Чекаємо трохи і перевіряємо чи запустився
    sleep 5
    
    if ps -p "$bot_pid" > /dev/null 2>&1; then
        log "INFO" "✅ Бот успішно запущено (PID: $bot_pid)"
        return 0
    else
        log "ERROR" "❌ Не вдалося запустити бота"
        rm -f "$PID_FILE"
        return 1
    fi
}

# Функція для перезапуску бота
restart_bot() {
    log "INFO" "🔄 Перезапуск бота..."
    stop_bot
    sleep 3
    start_bot
}

# Функція для перезапуску сервера
restart_server() {
    log "WARNING" "🔄 Перезапуск сервера через критичну помилку..."
    
    # Зберігаємо інформацію про перезапуск
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Server restart initiated by bot monitor" >> "$BOT_DIR/logs/server_restarts.log"
    
    # Перезапуск сервера
    sudo reboot
}

# Функція для перевірки здоров'я бота
health_check() {
    local attempt=1
    
    while [[ $attempt -le $MAX_RESTART_ATTEMPTS ]]; do
        log "INFO" "🔍 Перевірка стану бота (спроба $attempt/$MAX_RESTART_ATTEMPTS)..."
        
        if is_bot_running; then
            log "INFO" "✅ Бот працює нормально"
            return 0
        else
            log "WARNING" "⚠️ Бот не відповідає. Спроба перезапуску $attempt/$MAX_RESTART_ATTEMPTS"
            
            if [[ $attempt -eq 1 ]]; then
                # Перша спроба - чекаємо 1 хвилину і перевіряємо знову
                log "INFO" "⏱️ Очікування 1 хвилина перед перезапуском..."
                sleep 60
                
                if is_bot_running; then
                    log "INFO" "✅ Бот відновився самостійно"
                    return 0
                fi
            fi
            
            # Спроба перезапуску
            if restart_bot; then
                log "INFO" "✅ Бот успішно перезапущено"
                return 0
            else
                log "ERROR" "❌ Не вдалося перезапустити бота (спроба $attempt)"
                
                if [[ $attempt -eq $MAX_RESTART_ATTEMPTS ]]; then
                    log "CRITICAL" "🚨 Всі спроби перезапуску вичерпано. Перезапуск сервера..."
                    restart_server
                    exit 1
                fi
                
                # Чекаємо перед наступною спробою
                log "INFO" "⏱️ Очікування $RESTART_COOLDOWN секунд перед наступною спробою..."
                sleep $RESTART_COOLDOWN
            fi
        fi
        
        ((attempt++))
    done
    
    return 1
}

# Функція для ініціалізації
initialize() {
    # Створюємо директорію для логів якщо не існує
    mkdir -p "$BOT_DIR/logs"
    
    # Створюємо файл логів якщо не існує
    touch "$LOG_FILE"
    
    # Перевіряємо права доступу
    if [[ ! -w "$BOT_DIR" ]]; then
        echo "❌ Немає прав для запису в $BOT_DIR"
        exit 1
    fi
    
    # Перевіряємо наявність віртуального середовища
    if [[ ! -d "$VENV_PATH" ]]; then
        log "ERROR" "❌ Віртуальне середовище не знайдено: $VENV_PATH"
        log "INFO" "💡 Створіть віртуальне середовище: python3 -m venv $VENV_PATH"
        exit 1
    fi
    
    # Перевіряємо активацію віртуального середовища
    if [[ ! -f "$VENV_PATH/bin/activate" ]]; then
        log "ERROR" "❌ Файл активації не знайдено: $VENV_PATH/bin/activate"
        exit 1
    fi
    
    log "INFO" "🔧 Монітор бота ініціалізовано"
    log "INFO" "📁 Директорія бота: $BOT_DIR"
    log "INFO" "🐍 Віртуальне середовище: $VENV_PATH"
    log "INFO" "📝 Файл логів: $LOG_FILE"
    log "INFO" "⏰ Інтервал перевірки: $CHECK_INTERVAL секунд ($(($CHECK_INTERVAL/60)) хвилин)"
}

# Функція для обробки сигналів
cleanup() {
    log "INFO" "🛑 Отримано сигнал зупинки монітора"
    exit 0
}

# Встановлюємо обробники сигналів
trap cleanup SIGTERM SIGINT

# Основний цикл моніторингу
main_loop() {
    log "INFO" "🚀 Запуск моніторингу бота..."
    
    # Перевіряємо чи бот працює при запуску
    if ! is_bot_running; then
        log "INFO" "🔄 Бот не запущений при старті монітора. Запускаємо..."
        start_bot
    fi
    
    while true; do
        health_check
        
        log "INFO" "⏱️ Наступна перевірка через $(($CHECK_INTERVAL/60)) хвилин..."
        sleep $CHECK_INTERVAL
    done
}

# Функція показу статусу
show_status() {
    echo -e "${BLUE}=== BOT MONITOR STATUS ===${NC}"
    echo -e "Директорія бота: ${GREEN}$BOT_DIR${NC}"
    echo -e "Віртуальне середовище: ${GREEN}$VENV_PATH${NC}"
    echo -e "Файл логів: ${GREEN}$LOG_FILE${NC}"
    echo -e "PID файл: ${GREEN}$PID_FILE${NC}"
    echo ""
    
    # Перевірка віртуального середовища
    if [[ -d "$VENV_PATH" ]]; then
        echo -e "Віртуальне середовище: ${GREEN}ЗНАЙДЕНО${NC}"
    else
        echo -e "Віртуальне середовище: ${RED}НЕ ЗНАЙДЕНО${NC}"
    fi
    
    if is_bot_running; then
        local pid=$(pgrep -f "python.*$BOT_SCRIPT")
        echo -e "Статус бота: ${GREEN}ПРАЦЮЄ${NC} (PID: $pid)"
    else
        echo -e "Статус бота: ${RED}НЕ ПРАЦЮЄ${NC}"
    fi
    
    echo ""
    echo -e "Інтервал перевірки: ${YELLOW}$(($CHECK_INTERVAL/60)) хвилин${NC}"
    echo -e "Максимум спроб перезапуску: ${YELLOW}$MAX_RESTART_ATTEMPTS${NC}"
    echo ""
    
    if [[ -f "$LOG_FILE" ]]; then
        echo -e "${BLUE}=== ОСТАННІ ЗАПИСИ ЛОГУ ===${NC}"
        tail -10 "$LOG_FILE"
    fi
}

# Перевірка аргументів командного рядка
case "${1:-}" in
    "start")
        initialize
        main_loop
        ;;
    "stop")
        echo "🛑 Зупинка моніторингу..."
        pkill -f "monitor_bot.sh" 2>/dev/null
        echo "✅ Монітор зупинено"
        ;;
    "restart")
        echo "🔄 Перезапуск моніторингу..."
        pkill -f "monitor_bot.sh" 2>/dev/null
        sleep 2
        "$0" start &
        echo "✅ Монітор перезапущено"
        ;;
    "status")
        show_status
        ;;
    "check")
        initialize
        health_check
        ;;
    *)
        echo -e "${BLUE}=== BOT MONITOR SCRIPT ===${NC}"
        echo "Використання: $0 {start|stop|restart|status|check}"
        echo ""
        echo "Команди:"
        echo "  start   - Запустити моніторинг"
        echo "  stop    - Зупинити моніторинг"
        echo "  restart - Перезапустити моніторинг"
        echo "  status  - Показати статус"
        echo "  check   - Одноразова перевірка"
        exit 1
        ;;
esac
