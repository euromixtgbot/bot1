# ⚡ ШВИДКИЙ ГАЙД РОЗГОРТАННЯ БОТА

## 🚀 Автоматичне розгортання (рекомендовано)

```bash
# 1. Завантаження та запуск автоматичного скрипта
wget https://raw.githubusercontent.com/euromixtgbot/bot1/main/auto_deploy.sh
sudo chmod +x auto_deploy.sh
sudo ./auto_deploy.sh

# 2. Налаштування конфігурації (після завершення скрипта)
cd /home/Bot1/config
sudo cp credentials.env.template credentials.env
sudo cp service_account.json.template service_account.json
sudo nano credentials.env  # Заповніть токени та налаштування
sudo nano service_account.json  # Вставте Google Service Account

# 3. Запуск сервісів
sudo systemctl enable telegram-bot.service
sudo systemctl start telegram-bot.service
sudo systemctl status telegram-bot.service
```

## 🔧 Ручне розгортання (5 кроків)

### Крок 1: Підготовка сервера
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git curl
```

### Крок 2: Клонування проекту
```bash
cd /home
git clone https://github.com/euromixtgbot/bot1.git Bot1
cd Bot1
```

### Крок 3: Python середовище
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Крок 4: Конфігурація
```bash
cd config
cp credentials.env.template credentials.env
cp service_account.json.template service_account.json
nano credentials.env  # Заповніть дані
nano service_account.json  # Google Service Account
chmod 600 credentials.env service_account.json
```

### Крок 5: Systemd сервіс
```bash
sudo cp telegram-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable telegram-bot.service
sudo systemctl start telegram-bot.service
```

## 📋 Швидка перевірка

```bash
# Статус сервісів
sudo systemctl status telegram-bot.service bot-monitor.service

# Логи
tail -f /home/Bot1/logs/*.log

# Тест бота
curl -s "https://api.telegram.org/bot<YOUR_TOKEN>/getMe"
```

## 🆘 Швидке виправлення проблем

```bash
# Перезапуск всього
sudo systemctl restart telegram-bot.service bot-monitor.service

# Перевірка помилок
sudo journalctl -u telegram-bot.service -n 50

# Ручний запуск для дебагу
cd /home/Bot1
source venv/bin/activate
python src/main.py
```

## 🎯 Мінімальні вимоги

- **OS:** Ubuntu 22.04+
- **RAM:** 2GB
- **Python:** 3.10+
- **Мережа:** Доступ до api.telegram.org

## 📞 Налаштування токенів

1. **Telegram Bot Token:** @BotFather → /newbot
2. **Jira API Token:** Jira → Settings → Personal Access Tokens
3. **Google Service Account:** Google Cloud Console → APIs & Services → Credentials

**⏱️ Загальний час розгортання: 10-15 хвилин**
