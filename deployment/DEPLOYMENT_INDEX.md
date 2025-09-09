# 📚 ІНДЕКС ВСІХ ІНСТРУКЦІЙ РОЗГОРТАННЯ

## 🎯 Вибір підходящої інструкції:

### 🚀 Для швидкого старту (5 хвилин):
📄 **[QUICK_DEPLOY.md](QUICK_DEPLOY.md)**
- Автоматичне розгортання одним скриптом
- Мінімальні пояснення
- Для досвідчених адміністраторів

### 📖 Для детального розгортання (30 хвилин):
📄 **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)**
- Покрокова інструкція з поясненнями
- Повна документація процесу
- Troubleshooting секція
- Для новачків та детального розуміння

### ✅ Для контролю якості:
📄 **[deployment_checklist.md](deployment_checklist.md)**
- Чек-лист для системних адміністраторів
- Перевірка всіх етапів
- Фінальна валідація

### 🌐 Для додаткових функцій:
📄 **[DOMAIN_SSL_SETUP.md](DOMAIN_SSL_SETUP.md)**
- Налаштування домену та SSL
- Webhook замість polling
- Nginx конфігурація

---

## 🛠️ Автоматичні скрипти:

### 🤖 Повне автоматичне розгортання:
```bash
# Завантаження та запуск
wget https://raw.githubusercontent.com/euromixtgbot/bot1/main/deployment/auto_deploy.sh
sudo chmod +x auto_deploy.sh
sudo ./auto_deploy.sh
```

### 📊 Моніторинг та управління:
```bash
# Налаштування моніторингу
sudo /home/Bot1/monitoring/setup_monitoring.sh

# Контроль моніторингу
/home/Bot1/monitor_control.sh

# Створення безпечного backup
/home/Bot1/backups/create_secure_backup.sh

# АБО простий backup
/home/Bot1/create_backup.sh
```

---

## 📋 Етапи розгортання:

### 1️⃣ **Підготовка** (5 хвилин)
- Перевірка сервера
- Оновлення системи
- Встановлення базових пакетів

### 2️⃣ **Завантаження** (2 хвилини)
- Клонування репозиторію
- Перевірка файлів

### 3️⃣ **Python середовище** (3 хвилини)
- Створення venv
- Встановлення залежностей

### 4️⃣ **Конфігурація** (10 хвилин)
- Налаштування токенів
- Конфігурація API

### 5️⃣ **Сервіси** (5 хвилин)
- Systemd налаштування
- Автозапуск

### 6️⃣ **Моніторинг** (3 хвилини)
- Система спостереження
- Автоматичний перезапуск

### 7️⃣ **Тестування** (5 хвилин)
- Перевірка функціональності
- Валідація

---

## 🎯 Сценарії використання:

### 🟢 Новий сервер з нуля:
1. [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - детальна інструкція
2. [deployment_checklist.md](deployment_checklist.md) - валідація

### 🟡 Швидке розгортання:
1. [QUICK_DEPLOY.md](QUICK_DEPLOY.md) - 5 хвилин
2. `auto_deploy.sh` - автоматично

### 🔵 Міграція існуючого бота:
1. Backup поточних даних
2. [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - крок 4-7
3. Відновлення даних

### 🟣 Продуктивна система:
1. [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - повне розгортання
2. [DOMAIN_SSL_SETUP.md](DOMAIN_SSL_SETUP.md) - домен та SSL
3. [deployment_checklist.md](deployment_checklist.md) - валідація

---

## 🔧 Необхідні токени та доступи:

### 🤖 Telegram Bot:
- **Отримати:** @BotFather в Telegram
- **Команда:** `/newbot`
- **Формат:** `123456789:ABCdefGHIjklMNOpqrSTUvwxYZ`

### 🎫 Jira API:
- **Отримати:** Jira Settings → Personal Access Tokens
- **Необхідно:** Email, Domain, API Token, Project Key
- **Формат:** `ATATT3xFfGF0...`

### 📊 Google Sheets:
- **Отримати:** Google Cloud Console → APIs & Services
- **Необхідно:** Service Account JSON, Sheet ID
- **Доступ:** Надати read/write доступ Service Account

---

## 📊 Моніторинг після розгортання:

### 🔍 Команди перевірки:
```bash
# Статус сервісів
sudo systemctl status telegram-bot.service bot-monitor.service

# Логи реального часу
tail -f /home/Bot1/logs/*.log

# Статус процесів
ps aux | grep python | grep main.py

# Статус моніторингу
/home/Bot1/monitoring/monitor_bot.sh status
```

### 📈 Метрики успіху:
- ✅ Сервіси: Active (running)
- ✅ Бот відповідає на `/start`
- ✅ Логи без критичних помилок
- ✅ Автоматичний перезапуск працює

---

## 🆘 Швидка допомога:

### 🔴 Бот не запускається:
```bash
sudo journalctl -u telegram-bot.service -n 50
cd /home/Bot1 && source venv/bin/activate && python src/main.py
```

### 🟡 Конфігураційні помилки:
```bash
nano /home/Bot1/config/credentials.env
chmod 600 /home/Bot1/config/credentials.env
```

### 🟢 Перезапуск всієї системи:
```bash
sudo systemctl restart telegram-bot.service bot-monitor.service
```

---

## 📞 Підтримка:

### 📋 Документація:
- **Основна:** [README.md](README.md)
- **Моніторинг:** [MONITORING_README.md](MONITORING_README.md)
- **Backup:** Файли в `/home/Bot1/backups/`

### 🔗 Корисні посилання:
- **Telegram Bot API:** https://core.telegram.org/bots/api
- **Jira REST API:** https://developer.atlassian.com/cloud/jira/platform/rest/
- **Google Sheets API:** https://developers.google.com/sheets/api

**⏱️ Загальний час розгортання: 15-30 хвилин**  
**🎯 Результат: Повністю робочий Telegram бот з моніторингом**
