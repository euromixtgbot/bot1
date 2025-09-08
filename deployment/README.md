# 📦 DEPLOYMENT - ІНСТРУКЦІЇ ТА СКРИПТИ РОЗГОРТАННЯ

## 📁 Зміст папки:

### 📚 Інструкції розгортання:
- **[DEPLOYMENT_INDEX.md](DEPLOYMENT_INDEX.md)** - 📋 Індекс всіх інструкцій (ПОЧНІТЬ ЗВІДСИ)
- **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** - 📖 Повна детальна інструкція (30 хв)
- **[QUICK_DEPLOY.md](QUICK_DEPLOY.md)** - ⚡ Швидкий гайд (5 хв)
- **[DEPLOYMENT_README.md](DEPLOYMENT_README.md)** - 📋 Короткий огляд варіантів

### ✅ Контроль якості:
- **[deployment_checklist.md](deployment_checklist.md)** - 📋 Чек-лист для системних адміністраторів

### 🔧 Додаткові налаштування:
- **[DOMAIN_SSL_SETUP.md](DOMAIN_SSL_SETUP.md)** - 🌐 Налаштування домену та SSL (webhook)

### 🤖 Автоматизація:
- **[auto_deploy.sh](auto_deploy.sh)** - 🚀 Скрипт автоматичного розгортання

---

## 🎯 ШВИДКИЙ СТАРТ:

### Варіант 1: Автоматичне розгортання (найпростіший)
```bash
# Завантаження та запуск скрипта
wget https://raw.githubusercontent.com/euromixtgbot/bot1/main/deployment/auto_deploy.sh
chmod +x auto_deploy.sh
sudo ./auto_deploy.sh
```

### Варіант 2: Ручне розгортання за інструкцією
1. Прочитайте **[DEPLOYMENT_INDEX.md](DEPLOYMENT_INDEX.md)**
2. Виберіть підходящу інструкцію
3. Слідуйте покроковим інструкціям

---

## 📊 Структура розгортання:

```
🏗️ Процес розгортання:
├── 1️⃣ Підготовка сервера (5 хв)
├── 2️⃣ Завантаження коду (2 хв)
├── 3️⃣ Python середовище (3 хв)
├── 4️⃣ Конфігурація (10 хв)
├── 5️⃣ Systemd сервіси (5 хв)
├── 6️⃣ Система моніторингу (3 хв)
└── 7️⃣ Тестування (5 хв)

⏱️ Загальний час: 15-30 хвилин
```

---

## 🔧 Необхідні токени:

| Сервіс | Де отримати | Формат |
|--------|-------------|--------|
| **Telegram Bot** | @BotFather | `123456789:ABCdef...` |
| **Jira API** | Jira Settings | Email + Token |
| **Google Sheets** | Google Cloud Console | Service Account JSON |

---

## 🎯 Результат розгортання:

✅ **Повністю працюючий Telegram бот**  
✅ **Автоматичний моніторинг та перезапуск**  
✅ **Інтеграція з Jira та Google Sheets**  
✅ **Система логування та backup**  
✅ **Systemd автозапуск**  

---

## 🆘 Швидка допомога:

```bash
# Перевірка статусу після розгортання
sudo systemctl status telegram-bot.service bot-monitor.service

# Перегляд логів
tail -f /home/Bot1/logs/*.log

# Статус моніторингу
/home/Bot1/monitoring/monitor_bot.sh status
```

**💡 Почніть з файлу [DEPLOYMENT_INDEX.md](DEPLOYMENT_INDEX.md) для вибору найкращого варіанту!**
