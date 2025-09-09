#!/bin/bash

# =====================================
# АВТОМАТИЧНИЙ СКРИПТ РОЗГОРТАННЯ БОТА
# =====================================
# Цей скрипт автоматизує процес розгортання Telegram бота на новому сервері
# Використовуйте з обережністю на продуктивному сервері

set -e  # Зупинка при будь-якій помилці

# Кольори для виводу
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Конфігурація
BOT_DIR="/home/Bot1"
REPO_URL="https://github.com/euromixtgbot/bot1.git"
PYTHON_VERSION="3.12"
USER_HOME=$(eval echo ~$SUDO_USER)

# Функція логування
log() {
    local level=$1
    shift
    local message="$@"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "[$timestamp] ${BLUE}[$level]${NC} $message"
}

# Функція для запиту підтвердження
ask_confirmation() {
    local message="$1"
    echo -e "${YELLOW}$message${NC}"
    read -p "Продовжити? (y/N): " -r
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log "INFO" "Операція скасована користувачем"
        exit 0
    fi
}

# Перевірка прав root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        echo -e "${RED}❌ Цей скрипт повинен запускатися з правами root${NC}"
        echo "Використовуйте: sudo $0"
        exit 1
    fi
}

# Перевірка операційної системи
check_os() {
    log "INFO" "🔍 Перевірка операційної системи..."
    
    if [[ ! -f /etc/os-release ]]; then
        log "ERROR" "❌ Не вдається визначити операційну систему"
        exit 1
    fi
    
    source /etc/os-release
    
    if [[ "$ID" != "ubuntu" ]]; then
        log "WARNING" "⚠️ Цей скрипт оптимізовано для Ubuntu. Поточна ОС: $ID"
        ask_confirmation "Продовжити на власний ризик?"
    fi
    
    log "INFO" "✅ Операційна система: $PRETTY_NAME"
}

# Оновлення системи
update_system() {
    log "INFO" "🔄 Оновлення системи..."
    
    apt update
    apt upgrade -y
    
    log "INFO" "✅ Система оновлена"
}

# Встановлення системних пакетів
install_system_packages() {
    log "INFO" "📦 Встановлення системних пакетів..."
    
    apt install -y \
        python3 \
        python3-pip \
        python3-venv \
        python3-dev \
        git \
        curl \
        wget \
        htop \
        nano \
        vim \
        systemd \
        build-essential \
        libssl-dev \
        libffi-dev \
        software-properties-common \
        apt-transport-https \
        ca-certificates \
        gnupg \
        lsb-release
    
    log "INFO" "✅ Системні пакети встановлено"
}

# Перевірка версії Python
check_python_version() {
    log "INFO" "🐍 Перевірка версії Python..."
    
    local python_ver=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
    local required_ver="3.10"
    
    if [[ $(echo "$python_ver >= $required_ver" | bc -l) -eq 1 ]]; then
        log "INFO" "✅ Python версія $python_ver підходить (мінімум $required_ver)"
    else
        log "ERROR" "❌ Потрібна Python версія $required_ver або новіша. Поточна: $python_ver"
        exit 1
    fi
}

# Створення структури директорій
create_directory_structure() {
    log "INFO" "📁 Створення структури директорій..."
    
    # Видалення старої директорії якщо існує
    if [[ -d "$BOT_DIR" ]]; then
        log "WARNING" "⚠️ Директорія $BOT_DIR вже існує"
        ask_confirmation "Видалити існуючу директорію?"
        rm -rf "$BOT_DIR"
    fi
    
    # Створення основної директорії
    mkdir -p "$BOT_DIR"
    cd "$BOT_DIR"
    
    # Створення підкаталогів
    mkdir -p {src,config,logs,data,user_states,utils,scripts,reports,backups}
    
    log "INFO" "✅ Структура директорій створена"
}

# Клонування репозиторію
clone_repository() {
    log "INFO" "📥 Клонування репозиторію..."
    
    cd /home
    
    if [[ -d "Bot1" ]]; then
        rm -rf Bot1
    fi
    
    # Клонування репозиторію
    git clone "$REPO_URL" Bot1
    
    if [[ ! -d "Bot1" ]]; then
        log "ERROR" "❌ Не вдалося клонувати репозиторій"
        exit 1
    fi
    
    cd Bot1
    
    # Перевірка основних файлів
    if [[ ! -f "src/main.py" ]]; then
        log "ERROR" "❌ Основний файл src/main.py не знайдено"
        exit 1
    fi
    
    log "INFO" "✅ Репозиторій клоновано успішно"
}

# Створення віртуального середовища
create_virtual_environment() {
    log "INFO" "🔧 Створення віртуального середовища..."
    
    cd "$BOT_DIR"
    
    # Створення venv
    python3 -m venv venv
    
    # Активація
    source venv/bin/activate
    
    # Оновлення pip
    pip install --upgrade pip
    
    log "INFO" "✅ Віртуальне середовище створено"
}

# Встановлення Python залежностей
install_python_dependencies() {
    log "INFO" "📚 Встановлення Python залежностей..."
    
    cd "$BOT_DIR"
    source venv/bin/activate
    
    if [[ ! -f "requirements.txt" ]]; then
        log "ERROR" "❌ Файл requirements.txt не знайдено"
        exit 1
    fi
    
    # Встановлення залежностей
    pip install -r requirements.txt
    
    # Перевірка встановлення
    pip list | head -10
    
    log "INFO" "✅ Python залежності встановлено"
}

# Створення конфігураційних файлів
create_config_files() {
    log "INFO" "⚙️ Створення шаблонів конфігураційних файлів..."
    
    cd "$BOT_DIR/config"
    
    # Створення шаблону credentials.env
    cat > credentials.env.template << 'EOF'
# =====================================
# TELEGRAM BOT CONFIGURATION
# =====================================
TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN_HERE

# =====================================
# JIRA CONFIGURATION
# =====================================
JIRA_DOMAIN=https://your-company.atlassian.net
JIRA_EMAIL=your-email@company.com
JIRA_API_TOKEN=YOUR_JIRA_API_TOKEN_HERE
JIRA_PROJECT_KEY=YOUR_PROJECT_KEY
JIRA_ISSUE_TYPE=Task
JIRA_REPORTER_ACCOUNT_ID=YOUR_ACCOUNT_ID_HERE

# =====================================
# GOOGLE SHEETS CONFIGURATION
# =====================================
GOOGLE_CREDENTIALS_PATH=config/service_account.json
GOOGLE_SHEET_USERS_ID=YOUR_GOOGLE_SHEET_ID_HERE

# =====================================
# OTHER SETTINGS
# =====================================
FIELDS_MAPPING_FILE=fields_mapping.yaml
EOF

    # Створення шаблону service_account.json
    cat > service_account.json.template << 'EOF'
{
  "type": "service_account",
  "project_id": "your-project-id",
  "private_key_id": "your-private-key-id",
  "private_key": "-----BEGIN PRIVATE KEY-----\nYOUR_PRIVATE_KEY_HERE\n-----END PRIVATE KEY-----\n",
  "client_email": "your-service-account@your-project.iam.gserviceaccount.com",
  "client_id": "your-client-id",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/your-service-account%40your-project.iam.gserviceaccount.com"
}
EOF

    log "INFO" "✅ Шаблони конфігураційних файлів створено"
    log "WARNING" "⚠️ Не забудьте заповнити config/credentials.env та config/service_account.json"
}

# Налаштування прав доступу
set_permissions() {
    log "INFO" "🔐 Налаштування прав доступу..."
    
    # Встановлення власника
    chown -R $SUDO_USER:$SUDO_USER "$BOT_DIR"
    
    # Встановлення прав для директорій
    find "$BOT_DIR" -type d -exec chmod 755 {} \;
    
    # Встановлення прав для файлів
    find "$BOT_DIR" -type f -exec chmod 644 {} \;
    
    # Встановлення прав виконання для скриптів
    chmod +x "$BOT_DIR"/*.sh
    
    # Безпечні права для конфігурації
    if [[ -f "$BOT_DIR/config/credentials.env" ]]; then
        chmod 600 "$BOT_DIR/config/credentials.env"
    fi
    
    if [[ -f "$BOT_DIR/config/service_account.json" ]]; then
        chmod 600 "$BOT_DIR/config/service_account.json"
    fi
    
    log "INFO" "✅ Права доступу налаштовано"
}

# Створення systemd сервісів
create_systemd_services() {
    log "INFO" "🔧 Створення systemd сервісів..."
    
    # Основний сервіс бота
    cat > /etc/systemd/system/telegram-bot.service << EOF
[Unit]
Description=Telegram Bot Service
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=$SUDO_USER
WorkingDirectory=$BOT_DIR
ExecStart=$BOT_DIR/activate_and_run.sh
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Environment variables
Environment=PYTHONPATH=$BOT_DIR
Environment=PYTHONUNBUFFERED=1

# Security settings
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=$BOT_DIR

[Install]
WantedBy=multi-user.target
EOF

    # Перезавантаження systemd
    systemctl daemon-reload
    
    log "INFO" "✅ Systemd сервіси створено"
}

# Налаштування моніторингу
setup_monitoring() {
    log "INFO" "📊 Налаштування системи моніторингу..."
    
    cd "$BOT_DIR"
    
    if [[ -f "monitoring/setup_monitoring.sh" ]]; then
        chmod +x monitoring/setup_monitoring.sh
        ./monitoring/setup_monitoring.sh
        log "INFO" "✅ Система моніторингу налаштована"
    else
        log "WARNING" "⚠️ Скрипт monitoring/setup_monitoring.sh не знайдено"
    fi
}

# Налаштування системи backup
setup_backup_system() {
    log "INFO" "💾 Налаштування системи безпечного резервного копіювання..."
    
    cd "$BOT_DIR"
    
    # Перевірка наявності системи backup
    if [[ -f "backups/create_secure_backup.sh" ]]; then
        chmod +x backups/create_secure_backup.sh
        log "INFO" "✅ Безпечна система backup налаштована"
        
        # Створення символічного посилання для зручності
        ln -sf backups/create_secure_backup.sh create_backup.sh
        log "INFO" "✅ Створено зручне посилання: ./create_backup.sh"
    else
        log "WARNING" "⚠️ Система backup backups/create_secure_backup.sh не знайдена"
        log "INFO" "💾 Створення простого backup скрипта..."
        
        cat > "$BOT_DIR/create_backup.sh" << 'EOF'
#!/bin/bash

# Простий скрипт для створення резервної копії бота
BACKUP_DIR="/home/Bot1/backups"
DATE=$(date '+%Y%m%d_%H%M%S')
BACKUP_NAME="Bot1_simple_backup_${DATE}"

# Створення директорії для backup
mkdir -p "$BACKUP_DIR"

# Створення архіву (без логів та кешу)
cd /home
tar -czf "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" \
    --exclude='Bot1/logs/*' \
    --exclude='Bot1/venv' \
    --exclude='Bot1/__pycache__' \
    --exclude='Bot1/*/__pycache__' \
    --exclude='Bot1/user_states/*.json' \
    --exclude='Bot1/config/credentials.env' \
    --exclude='Bot1/config/service_account.json' \
    Bot1/

echo "✅ Backup створено: ${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
ls -lh "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
EOF

        chmod +x "$BOT_DIR/create_backup.sh"
        log "INFO" "✅ Простий скрипт backup створено"
    fi
}

# Фінальна перевірка
final_check() {
    log "INFO" "🔍 Фінальна перевірка встановлення..."
    
    local errors=0
    
    # Перевірка директорій
    if [[ ! -d "$BOT_DIR" ]]; then
        log "ERROR" "❌ Директорія $BOT_DIR не існує"
        ((errors++))
    fi
    
    # Перевірка віртуального середовища
    if [[ ! -d "$BOT_DIR/venv" ]]; then
        log "ERROR" "❌ Віртуальне середовище не створено"
        ((errors++))
    fi
    
    # Перевірка основних файлів
    local required_files=(
        "src/main.py"
        "requirements.txt"
        "activate_and_run.sh"
        "monitoring/monitor_bot.sh"
    )
    
    for file in "${required_files[@]}"; do
        if [[ ! -f "$BOT_DIR/$file" ]]; then
            log "ERROR" "❌ Файл $file не знайдено"
            ((errors++))
        fi
    done
    
    # Перевірка systemd сервісу
    if [[ ! -f "/etc/systemd/system/telegram-bot.service" ]]; then
        log "ERROR" "❌ Systemd сервіс не створено"
        ((errors++))
    fi
    
    if [[ $errors -eq 0 ]]; then
        log "INFO" "✅ Всі перевірки пройдено успішно"
        return 0
    else
        log "ERROR" "❌ Знайдено $errors помилок"
        return 1
    fi
}

# Показ наступних кроків
show_next_steps() {
    echo -e "${GREEN}"
    echo "========================================"
    echo "🎉 РОЗГОРТАННЯ ЗАВЕРШЕНО УСПІШНО!"
    echo "========================================"
    echo -e "${NC}"
    
    echo -e "${YELLOW}📋 НАСТУПНІ КРОКИ:${NC}"
    echo ""
    
    echo -e "${BLUE}1. Налаштування конфігурації:${NC}"
    echo "   cd $BOT_DIR/config"
    echo "   cp credentials.env.template credentials.env"
    echo "   cp service_account.json.template service_account.json"
    echo "   nano credentials.env"
    echo "   nano service_account.json"
    echo ""
    
    echo -e "${BLUE}2. Встановлення прав доступу:${NC}"
    echo "   chmod 600 $BOT_DIR/config/credentials.env"
    echo "   chmod 600 $BOT_DIR/config/service_account.json"
    echo ""
    
    echo -e "${BLUE}3. Тестування бота:${NC}"
    echo "   cd $BOT_DIR"
    echo "   source venv/bin/activate"
    echo "   python src/main.py"
    echo ""
    
    echo -e "${BLUE}4. Запуск сервісів:${NC}"
    echo "   sudo systemctl enable telegram-bot.service"
    echo "   sudo systemctl start telegram-bot.service"
    echo "   sudo systemctl status telegram-bot.service"
    echo ""
    
    echo -e "${BLUE}5. Перевірка моніторингу:${NC}"
    echo "   $BOT_DIR/monitoring/monitor_bot.sh status"
    echo "   sudo systemctl status bot-monitor.service"
    echo ""
    
    echo -e "${BLUE}6. Створення backup:${NC}"
    echo "   $BOT_DIR/create_backup.sh"
    echo "   # АБО використовуйте безпечну систему:"
    echo "   $BOT_DIR/backups/create_secure_backup.sh"
    echo ""
    
    echo -e "${GREEN}📚 Детальна документація: $BOT_DIR/deployment/DEPLOYMENT_GUIDE.md${NC}"
    echo -e "${GREEN}🗂️ Система звітів: $BOT_DIR/reports/ (організовано за датами)${NC}"
    echo -e "${GREEN}💾 Система backup: $BOT_DIR/backups/README.md${NC}"
    echo -e "${GREEN}🆘 У разі проблем: $BOT_DIR/README.md${NC}"
}

# Головна функція
main() {
    echo -e "${PURPLE}"
    echo "========================================"
    echo "🚀 АВТОМАТИЧНЕ РОЗГОРТАННЯ TELEGRAM БОТА"
    echo "========================================"
    echo -e "${NC}"
    
    log "INFO" "🎯 Початок автоматичного розгортання..."
    
    # Перевірки
    check_root
    check_os
    
    # Підтвердження
    ask_confirmation "Почати автоматичне розгортання Telegram бота?"
    
    # Основні кроки
    update_system
    install_system_packages
    check_python_version
    create_directory_structure
    clone_repository
    create_virtual_environment
    install_python_dependencies
    create_config_files
    set_permissions
    create_systemd_services
    setup_monitoring
    setup_backup_system
    
    # Фінальна перевірка
    if final_check; then
        show_next_steps
        log "INFO" "🎉 Розгортання завершено успішно!"
    else
        log "ERROR" "❌ Розгортання завершено з помилками"
        exit 1
    fi
}

# Запуск скрипта
main "$@"
