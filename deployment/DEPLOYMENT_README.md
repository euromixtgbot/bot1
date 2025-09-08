# 📦 ФАЙЛИ ДЛЯ РОЗГОРТАННЯ БОТА НА НОВОМУ СЕРВЕРІ

## 📁 Структура файлів розгортання:

```
📂 Файли для розгортання:
├── 📄 DEPLOYMENT_GUIDE.md      # Повна детальна інструкція (крок за кроком)
├── 🚀 auto_deploy.sh           # Автоматичний скрипт розгортання
├── ⚡ QUICK_DEPLOY.md          # Швидкий гайд (5 хвилин)
└── 📋 deployment_checklist.md  # Чек-лист для адміністраторів
```

## 🎯 Варіанти розгортання:

### 🟢 Варіант 1: Автоматичне розгортання (найпростіший)
```bash
wget https://raw.githubusercontent.com/euromixtgbot/bot1/main/auto_deploy.sh
sudo chmod +x auto_deploy.sh
sudo ./auto_deploy.sh
```

### 🟡 Варіант 2: Швидке ручне розгортання (5 кроків)
Дивіться: `QUICK_DEPLOY.md`

### 🔴 Варіант 3: Повне ручне розгортання
Дивіться: `DEPLOYMENT_GUIDE.md`

## 📋 Що потрібно підготувати:

1. **Сервер Ubuntu 22.04+** з root доступом
2. **Telegram Bot Token** (@BotFather)
3. **Jira API credentials** (домен, email, токен)
4. **Google Service Account JSON** (для Google Sheets)
5. **Google Sheet ID** (для зберігання користувачів)

## 🎉 Після розгортання:

✅ Бот автоматично запускається  
✅ Система моніторингу працює  
✅ Автоматичний перезапуск при збоях  
✅ Backup система налаштована  
✅ Логування активне  

## 🆘 Підтримка:

- **Логи:** `/home/Bot1/logs/`
- **Статус:** `sudo systemctl status telegram-bot.service`
- **Моніторинг:** `/home/Bot1/monitoring/monitor_bot.sh status`

**⏱️ Час розгортання: 10-15 хвилин**
