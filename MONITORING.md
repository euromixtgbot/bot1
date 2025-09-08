# 📊 СИСТЕМА МОНІТОРИНГУ БОТА

## 📂 Папка з інструкціями: **[monitoring/](monitoring/)**

### 🎯 Швидкий старт:

1. **Перейдіть до папки:** [monitoring/](monitoring/)
2. **Почніть з файлу:** [monitoring/README.md](monitoring/README.md)
3. **Виберіть підходящий варіант управління**

---

## ⚡ Найшвидший спосіб (1 команда):

```bash
sudo /home/Bot1/monitoring/setup_monitoring.sh
```

---

## 🎛️ Варіанти управління:

| Варіант | Призначення | Файл |
|---------|-------------|------|
| 🚀 **Автоналаштування** | Повне налаштування системи | [setup_monitoring.sh](monitoring/setup_monitoring.sh) |
| 🎛️ **Інтерактивне меню** | Управління через інтерфейс | [monitor_control.sh](monitoring/monitor_control.sh) |
| 🎯 **Прямі команди** | Швидкі команди статусу | [monitor_bot.sh](monitoring/monitor_bot.sh) |

---

## 🔧 Швидкі команди:

```bash
# Статус системи моніторингу
/home/Bot1/monitoring/monitor_bot.sh status

# Інтерактивне управління  
sudo /home/Bot1/monitoring/monitor_control.sh

# Ручна перевірка зараз
/home/Bot1/monitoring/monitor_bot.sh check
```

---

## 🎯 Що забезпечує:

- ✅ Автоматична перевірка кожні 15 хвилин
- ✅ Автоперезапуск при збоях (до 3 спроб)  
- ✅ Systemd інтеграція з автозапуском
- ✅ Детальне логування операцій
- ✅ Перезапуск сервера при критичних помилках

**📂 Всі інструкції та скрипти знаходяться в папці [monitoring/](monitoring/)**
