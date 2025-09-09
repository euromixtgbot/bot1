# 🚀 ПОВНА ІНСТРУКЦІЯ РОЗГОРТАННЯ TELEGRAM БОТА НА НОВОМУ СЕРВЕРІ

**Дата створення:** 8 вересня 2025  
**Версія:** Production Ready  
**Статус:** Повна робоча копія з моніторингом

---

## 📋 ЗМІСТ

1. [Вимоги до сервера](#1-вимоги-до-сервера)
2. [Підготовка сервера](#2-підготовка-сервера)
3. [Створення користувача та структури](#3-створення-користувача-та-структури)
4. [Завантаження коду проекту](#4-завантаження-коду-проекту)
5. [Налаштування Python середовища](#5-налаштування-python-середовища)
6. [Конфігурація проекту](#6-конфігурація-проекту)
7. [Налаштування сервісів](#7-налаштування-сервісів)
8. [Система моніторингу](#8-система-моніторингу)
9. [Запуск та тестування](#9-запуск-та-тестування)
10. [Налагодження проблем](#10-налагодження-проблем)
11. [Резервне копіювання](#11-резервне-копіювання)

---

## 1. ВИМОГИ ДО СЕРВЕРА

### 🖥️ Мінімальні характеристики:
- **OS:** Ubuntu 22.04 LTS або новіше (рекомендовано 24.04 LTS)
- **RAM:** 2 GB (рекомендовано 4 GB)
- **CPU:** 2 vCPU (рекомендовано 4 vCPU)
- **Диск:** 20 GB SSD (рекомендовано 40 GB)
- **Мережа:** Стабільне з'єднання з інтернетом

### 🔗 Необхідні сервіси:
- **Telegram Bot Token** (отримати у @BotFather)
- **Jira API токен** та доступ до інстансу
- **Google Sheets API** (Service Account)
- **Доменне ім'я** (опціонально для webhook)

---

## 2. ПІДГОТОВКА СЕРВЕРА

### Крок 2.1: Оновлення системи
```bash
# Оновлення пакетного менеджера
sudo apt update && sudo apt upgrade -y

# Встановлення необхідних системних пакетів
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
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
    python3-dev
```

### Крок 2.2: Налаштування firewall (якщо потрібно)
```bash
# Увімкнення firewall
sudo ufw enable

# Дозвіл SSH
sudo ufw allow ssh

# Дозвіл HTTP/HTTPS (якщо використовуєте webhook)
sudo ufw allow 80
sudo ufw allow 443

# Перевірка статусу
sudo ufw status
```

### Крок 2.3: Налаштування часового поясу
```bash
# Встановлення часового поясу
sudo timedatectl set-timezone Europe/Kiev

# Перевірка
timedatectl status
```

---

## 3. СТВОРЕННЯ КОРИСТУВАЧА ТА СТРУКТУРИ

### Крок 3.1: Створення користувача (опціонально)
```bash
# Створення користувача для бота
sudo adduser botuser

# Додавання до sudo групи
sudo usermod -aG sudo botuser

# Перехід на користувача
sudo su - botuser
```

### Крок 3.2: Створення структури директорій
```bash
# Створення основної директорії
sudo mkdir -p /home/Bot1
cd /home/Bot1

# Створення структури проекту
sudo mkdir -p {src,config,logs,data,user_states,utils,scripts,reports,backups}

# Встановлення прав доступу
sudo chown -R $USER:$USER /home/Bot1
chmod -R 755 /home/Bot1
```

---

## 4. ЗАВАНТАЖЕННЯ КОДУ ПРОЕКТУ

### Метод 1: Клонування з GitHub
```bash
# Перехід в робочу директорію
cd /home

# Клонування репозиторію
git clone https://github.com/euromixtgbot/bot1.git Bot1

# Перехід в директорію проекту
cd Bot1

# Перевірка структури
ls -la
```

### Метод 2: Відновлення з backup архіву
```bash
# Якщо у вас є backup архів
cd /home

# Завантаження архіву (замініть URL на актуальний)
wget https://example.com/Bot1_backup_YYYYMMDD_version.tar.gz

# Розпакування
tar -xzf Bot1_backup_YYYYMMDD_version.tar.gz

# Встановлення прав
chown -R $USER:$USER /home/Bot1
```

### Крок 4.1: Перевірка структури проекту
```bash
cd /home/Bot1

# Перевірка основних файлів
ls -la

# Перевірка структури src
ls -la src/

# Перевірка конфігурації
ls -la config/
```

**Очікувана структура:**
```
Bot1/
├── src/                          # Основний код
│   ├── main.py                  # Точка входу
│   ├── handlers.py              # Обробники повідомлень
│   ├── keyboards.py             # Клавіатури
│   ├── services.py              # Jira API сервіси
│   ├── user_management_service.py
│   ├── user_state_service.py
│   ├── google_sheets_service.py
│   └── constants.py
├── config/                      # Конфігурація
│   ├── config.py
│   ├── credentials.env          # Буде створено пізніше
│   ├── fields_mapping.yaml
│   └── service_account.json     # Буде створено пізніше
├── requirements.txt             # Python залежності
├── activate_and_run.sh          # Скрипт запуску
├── monitoring/monitor_bot.sh              # Скрипт моніторингу
├── monitoring/setup_monitoring.sh         # Налаштування моніторингу
├── README.md                   # Документація
└── logs/                       # Логи
```

---

## 5. НАЛАШТУВАННЯ PYTHON СЕРЕДОВИЩА

### Крок 5.1: Створення віртуального середовища
```bash
cd /home/Bot1

# Створення віртуального середовища
python3 -m venv venv

# Активація віртуального середовища
source venv/bin/activate

# Оновлення pip
pip install --upgrade pip

# Перевірка версії Python
python --version
pip --version
```

### Крок 5.2: Встановлення залежностей
```bash
# Активація середовища (якщо не активоване)
source venv/bin/activate

# Встановлення всіх залежностей
pip install -r requirements.txt

# Перевірка встановлених пакетів
pip list

# Збереження точних версій (опціонально)
pip freeze > requirements_frozen.txt
```

### Крок 5.3: Налаштування PYTHONPATH
```bash
# Додавання до ~/.bashrc
echo 'export PYTHONPATH=/home/Bot1:$PYTHONPATH' >> ~/.bashrc

# Застосування змін
source ~/.bashrc

# Перевірка
echo $PYTHONPATH
```

---

## 6. КОНФІГУРАЦІЯ ПРОЕКТУ

### Крок 6.1: Створення файлу credentials.env
```bash
cd /home/Bot1/config

# Створення файлу конфігурації
nano credentials.env
```

**Вміст файлу credentials.env:**
```env
# =====================================
# TELEGRAM BOT CONFIGURATION
# =====================================
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

# =====================================
# JIRA CONFIGURATION
# =====================================
JIRA_DOMAIN=https://your-company.atlassian.net
JIRA_EMAIL=your-email@company.com
JIRA_API_TOKEN=your_jira_api_token_here
JIRA_PROJECT_KEY=YOUR_PROJECT_KEY
JIRA_ISSUE_TYPE=Task
JIRA_REPORTER_ACCOUNT_ID=your_account_id_here

# =====================================
# GOOGLE SHEETS CONFIGURATION
# =====================================
GOOGLE_CREDENTIALS_PATH=config/service_account.json
GOOGLE_SHEET_USERS_ID=your_google_sheet_id_here

# =====================================
# WEBHOOK CONFIGURATION (опціонально)
# =====================================
# WEBHOOK_URL=https://yourdomain.com/webhook
# WEBHOOK_HOST=0.0.0.0
# WEBHOOK_PORT=8443
# SSL_CERT_PATH=/path/to/cert.pem
# SSL_KEY_PATH=/path/to/private.key

# =====================================
# OTHER SETTINGS
# =====================================
FIELDS_MAPPING_FILE=fields_mapping.yaml
```

### Крок 6.2: Налаштування Google Service Account
```bash
cd /home/Bot1/config

# Створення файлу service_account.json
nano service_account.json
```

**Вміст файлу service_account.json** (отримати з Google Cloud Console):
```json
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
```

### Крок 6.3: Встановлення прав доступу
```bash
# Встановлення безпечних прав для конфігураційних файлів
chmod 600 /home/Bot1/config/credentials.env
chmod 600 /home/Bot1/config/service_account.json

# Перевірка прав
ls -la /home/Bot1/config/
```

---

## 7. НАЛАШТУВАННЯ СЕРВІСІВ

### Крок 7.1: Створення скрипта запуску
```bash
# Перевірка наявності activate_and_run.sh
ls -la /home/Bot1/activate_and_run.sh

# Встановлення прав виконання
chmod +x /home/Bot1/activate_and_run.sh

# Тестування скрипта
./activate_and_run.sh --help
```

### Крок 7.2: Тестування запуску бота
```bash
cd /home/Bot1

# Активація віртуального середовища
source venv/bin/activate

# Тестовий запуск бота
python src/main.py

# Якщо все працює, зупиняємо (Ctrl+C)
```

### Крок 7.3: Налаштування автозапуску через systemd
```bash
# Створення systemd сервісу
sudo nano /etc/systemd/system/telegram-bot.service
```

**Вміст файлу telegram-bot.service:**
```ini
[Unit]
Description=Telegram Bot Service
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=root
WorkingDirectory=/home/Bot1
ExecStart=/home/Bot1/activate_and_run.sh
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Environment variables
Environment=PYTHONPATH=/home/Bot1
Environment=PYTHONUNBUFFERED=1

# Security settings
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/home/Bot1

[Install]
WantedBy=multi-user.target
```

### Крок 7.4: Активація сервісу
```bash
# Перезавантаження systemd конфігурації
sudo systemctl daemon-reload

# Увімкнення автозапуску
sudo systemctl enable telegram-bot.service

# Запуск сервісу
sudo systemctl start telegram-bot.service

# Перевірка статусу
sudo systemctl status telegram-bot.service

# Перегляд логів
sudo journalctl -u telegram-bot.service -f
```

---

## 8. СИСТЕМА МОНІТОРИНГУ

### Крок 8.1: Налаштування скрипта моніторингу
```bash
cd /home/Bot1

# Встановлення прав виконання
chmod +x monitoring/monitor_bot.sh
chmod +x monitoring/setup_monitoring.sh

# Перевірка скрипта моніторингу
./monitoring/monitor_bot.sh status
```

### Крок 8.2: Запуск автоматичного налаштування
```bash
cd /home/Bot1

# Запуск скрипта налаштування моніторингу
sudo ./monitoring/setup_monitoring.sh

# Перевірка статусу сервісу моніторингу
sudo systemctl status bot-monitor.service

# Перегляд логів моніторингу
tail -f logs/monitor.log
```

### Крок 8.3: Ручне налаштування моніторингу (якщо потрібно)
```bash
# Копіювання systemd сервісу для моніторингу
sudo cp bot-monitor.service /etc/systemd/system/

# Перезавантаження systemd
sudo systemctl daemon-reload

# Увімкнення автозапуску моніторингу
sudo systemctl enable bot-monitor.service

# Запуск моніторингу
sudo systemctl start bot-monitor.service

# Перевірка статусу
sudo systemctl status bot-monitor.service
```

---

## 9. ЗАПУСК ТА ТЕСТУВАННЯ

### Крок 9.1: Перевірка всіх сервісів
```bash
# Перевірка статусу основного бота
sudo systemctl status telegram-bot.service

# Перевірка статусу моніторингу
sudo systemctl status bot-monitor.service

# Перевірка процесів
ps aux | grep python
```

### Крок 9.2: Тестування функціональності бота
```bash
# Перегляд логів бота
tail -f logs/bot_*.log

# Перегляд логів моніторингу
tail -f logs/monitor.log

# Перегляд системних логів
sudo journalctl -u telegram-bot.service -f
```

### Крок 9.3: Тестування в Telegram
1. Відкрийте Telegram
2. Знайдіть вашого бота за username
3. Натисніть `/start`
4. Перевірте реєстрацію через номер телефону
5. Протестуйте створення задач в Jira
6. Перевірте інтеграцію з Google Sheets

### Крок 9.4: Перевірка автоматичного перезапуску
```bash
# Симуляція збою бота
sudo pkill -f "python.*main.py"

# Перевірка через 1-2 хвилини чи перезапустився
ps aux | grep python

# Перегляд логів моніторингу
tail -f logs/monitor.log
```

---

## 10. НАЛАГОДЖЕННЯ ПРОБЛЕМ

### 🔍 Часті проблеми та рішення:

#### Проблема 1: Бот не запускається
```bash
# Перевірка логів
sudo journalctl -u telegram-bot.service -n 50

# Перевірка конфігурації
cat config/credentials.env

# Тестування вручну
cd /home/Bot1
source venv/bin/activate
python src/main.py
```

#### Проблема 2: Помилки з віртуальним середовищем
```bash
# Перестворення віртуального середовища
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### Проблема 3: Проблеми з правами доступу
```bash
# Встановлення правильних прав
sudo chown -R $USER:$USER /home/Bot1
chmod -R 755 /home/Bot1
chmod 600 /home/Bot1/config/credentials.env
chmod 600 /home/Bot1/config/service_account.json
```

#### Проблема 4: Мережеві проблеми
```bash
# Перевірка з'єднання з Telegram
curl -s https://api.telegram.org/bot<YOUR_TOKEN>/getMe

# Перевірка DNS
nslookup api.telegram.org

# Перевірка firewall
sudo ufw status
```

### 📊 Команди діагностики:
```bash
# Загальний статус системи
./monitoring/monitor_bot.sh status

# Перевірка всіх сервісів
sudo systemctl status telegram-bot.service bot-monitor.service

# Перевірка процесів
ps aux | grep -E "(python|monitor)"

# Перевірка логів
tail -f logs/*.log

# Перевірка дискового простору
df -h

# Перевірка пам'яті
free -h

# Перевірка мережі
ping google.com
```

---

## 11. РЕЗЕРВНЕ КОПІЮВАННЯ

### Крок 11.1: Безпечна система backup
```bash
cd /home/Bot1

# Перевірка наявності безпечної системи backup
if [[ -f "backups/create_secure_backup.sh" ]]; then
    echo "✅ Безпечна система backup вже доступна"
    chmod +x backups/create_secure_backup.sh
    
    # Створення зручного посилання
    ln -sf backups/create_secure_backup.sh create_backup.sh
    
    # Перегляд документації
    cat backups/README.md
else
    echo "⚠️ Безпечна система backup не знайдена, створюємо простий варіант"
    
    # Створення простого скрипта backup
    cat > create_backup.sh << 'EOF'
#!/bin/bash

# Простий скрипт для створення резервної копії бота
BACKUP_DIR="/home/Bot1/backups"
DATE=$(date '+%Y%m%d_%H%M%S')
BACKUP_NAME="Bot1_simple_backup_${DATE}"

# Створення директорії для backup
mkdir -p "$BACKUP_DIR"

# Створення архіву (без логів, конфіденційних даних та кешу)
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

    chmod +x create_backup.sh
fi
```

### Крок 11.2: Використання безпечного backup
```bash
# Створення безпечного backup (рекомендовано)
./backups/create_secure_backup.sh

# АБО використання простого варіанту
./create_backup.sh

# Перевірка створеного backup
ls -la backups/*.tar.gz
```

### Крок 11.3: Автоматичні backup через cron
```bash
# Редагування crontab
crontab -e

# Додавання записів (безпечний backup кожен день о 3:00)
0 3 * * * /home/Bot1/backups/create_secure_backup.sh >> /home/Bot1/logs/backup.log 2>&1

# Очищення старих backup (старше 30 днів)
0 4 * * * find /home/Bot1/backups -name "*.tar.gz" -mtime +30 -delete
```

### Крок 11.4: Переваги безпечної системи backup
- ✅ **Виключає конфіденційні дані** (токени, паролі)
- ✅ **Виключає логи** (можуть містити чутливу інформацію)
- ✅ **Компактний розмір** (~484KB замість мегабайтів)
- ✅ **Повна документація** відновлення
- ✅ **Автоматична перевірка** безпеки
- ✅ **Готові шаблони** конфігурації

### Крок 11.3: Ручне створення backup
```bash
# Створення backup зараз
./create_backup.sh

# Перевірка створених backup
ls -la backups/
```

---

## 🎉 ФІНАЛЬНА ПЕРЕВІРКА

### ✅ Чек-лист успішного розгортання:

1. **Сервер підготовлено:**
   - [ ] Ubuntu встановлено та оновлено
   - [ ] Python 3.12+ встановлено
   - [ ] Системні пакети встановлено

2. **Проект налаштовано:**
   - [ ] Код завантажено з GitHub або backup
   - [ ] Віртуальне середовище створено
   - [ ] Залежності встановлено
   - [ ] Конфігурація налаштована

3. **Сервіси працюють:**
   - [ ] telegram-bot.service активний
   - [ ] bot-monitor.service активний
   - [ ] Автозапуск увімкнено

4. **Моніторинг працює:**
   - [ ] Автоматична перевірка кожні 15 хвилин
   - [ ] Автоматичний перезапуск при збоях
   - [ ] Логування працює

5. **Бот функціонує:**
   - [ ] Відповідає на /start
   - [ ] Реєстрація працює
   - [ ] Створення задач в Jira працює
   - [ ] Інтеграція з Google Sheets працює

6. **Backup налаштовано:**
   - [ ] Скрипт backup створено
   - [ ] Автоматичні backup через cron
   - [ ] Очищення старих backup

### 🚀 Команди для швидкої перевірки:
```bash
# Перевірка всього за раз
cd /home/Bot1
echo "=== СТАТУС СЕРВІСІВ ==="
sudo systemctl status telegram-bot.service bot-monitor.service

echo -e "\n=== СТАТУС ПРОЦЕСІВ ==="
ps aux | grep -E "(python.*main.py|monitoring/monitor_bot.sh)"

echo -e "\n=== ОСТАННІ ЛОГИ ==="
tail -5 logs/monitor.log

echo -e "\n=== СТАТУС МОНІТОРИНГУ ==="
./monitoring/monitor_bot.sh status
```

---

## 📞 ПІДТРИМКА

### 🆘 У разі проблем:
1. Перевірте логи: `tail -f logs/*.log`
2. Перевірте сервіси: `sudo systemctl status telegram-bot.service`
3. Перевірте моніторинг: `./monitoring/monitor_bot.sh status`
4. Створіть backup: `./create_backup.sh`

### 📚 Корисні команди:
```bash
# Перезапуск всієї системи
sudo systemctl restart telegram-bot.service bot-monitor.service

# Перегляд всіх логів
sudo journalctl -u telegram-bot.service -u bot-monitor.service -f

# Перевірка мережевого з'єднання
curl -s https://api.telegram.org/bot<TOKEN>/getMe

# Очищення логів (при потребі)
sudo journalctl --vacuum-time=7d
```

**🎯 Готово! Ваш Telegram бот повністю налаштований та готовий до роботи!**
