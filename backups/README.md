# 🗂️ Система бекапів Bot1

**Оновлено:** 2025-09-09  
**Проект:** Bot1 Telegram Bot with Jira Integration  

## 📋 Огляд

Ця папка містить систему створення безпечних бекапів проекту Bot1. Система забезпечує створення архівів проекту без конфіденційної інформації та логів, що робить їх безпечними для зберігання та передачі.

## 📁 Файли в папці

### `create_secure_backup.sh`
**Призначення:** Основний скрипт для створення безпечних бекапів  
**Тип:** Виконуваний bash-скрипт  
**Розмір:** ~8KB  

### `Bot1_secure_backup_YYYYMMDD_HHMMSS.tar.gz`
**Призначення:** Архіви безпечних бекапів  
**Формат:** Gzip-стислий tar архів  
**Номенклатура:** Дата та час створення в форматі ISO  

## 🚀 Швидкий старт

### Створення нового бекапу
```bash
cd /home/Bot1/backups
./create_secure_backup.sh
```

### Перегляд списку бекапів
```bash
cd /home/Bot1/backups
ls -lh *.tar.gz
```

### Перевірка вмісту бекапу
```bash
cd /home/Bot1/backups
tar -tzf Bot1_secure_backup_YYYYMMDD_HHMMSS.tar.gz | head -20
```

## 🔒 Безпека бекапів

### ✅ Що ВКЛЮЧАЄТЬСЯ в бекап:
- **Вихідний код:** `src/`, `utils/`, `Tests/`
- **Скрипти:** `scripts/` (без логів), `monitoring/` (без логів)
- **Конфігурація:** Публічні файли конфігурації
- **Документація:** `reports/`, `*.md` файли
- **Налаштування:** `pyproject.toml`, `requirements.txt`, `.vscode/`
- **Шаблони:** `config/credentials.env.template`
- **Розгортання:** `deployment/`

### ❌ Що ВИКЛЮЧАЄТЬСЯ з бекапу:
- **Конфіденційні дані:**
  - `config/credentials.env` (реальні токени)
  - `config/service_account.json` (ключі Google)
  - `config/field_values.json` (можуть містити конфіденційну інформацію)
  
- **Логи та тимчасові файли:**
  - `logs/` (всі системні логи)
  - `scripts/logs/` (логи скриптів)
  - `monitoring/logs/` (логи моніторингу)
  - `*.log` (всі лог файли)
  - `*.pid` (PID файли процесів)
  
- **Робочі дані:**
  - `user_states/` (стани користувачів)
  - `data/` (робочі дані)
  - `venv/` (віртуальне середовище)
  - `__pycache__/` (кеш Python)
  - `.git/` (Git репозиторій)
  - `backups/` (попередні бекапи)

## 📊 Статистика бекапів

### Типовий розмір бекапу: ~484KB
### Кількість файлів: ~209
### Час створення: ~1-2 секунди

## 🔧 Відновлення з бекапу

### 1. Розпакування
```bash
# Створити папку для відновлення
mkdir /tmp/bot1_restore
cd /tmp/bot1_restore

# Розпакувати бекап
tar -xzf /path/to/Bot1_secure_backup_YYYYMMDD_HHMMSS.tar.gz
```

### 2. Налаштування конфіденційних файлів
```bash
cd Bot1_secure_backup_YYYYMMDD_HHMMSS

# Створити конфіденційні файли з шаблонів
cp config/credentials.env.template config/credentials.env

# Заповнити реальні значення в credentials.env:
# BOT_TOKEN=your_bot_token_here
# JIRA_URL=your_jira_url
# JIRA_USERNAME=your_username
# JIRA_API_TOKEN=your_api_token
```

### 3. Створення віртуального середовища
```bash
# Створити віртуальне середовище
python -m venv venv

# Активувати середовище
source venv/bin/activate  # Linux/Mac
# або
venv\Scripts\activate     # Windows

# Встановити залежності
pip install -r requirements.txt
```

### 4. Створення робочих папок
```bash
# Створити необхідні папки
mkdir -p logs data user_states

# Встановити права доступу
chmod 755 logs data user_states
```

### 5. Перевірка відновлення
```bash
# Перевірити конфігурацію
python -c "from config.config import load_config; print('Config OK')"

# Запустити тести (якщо є)
python -m pytest Tests/ -v
```

## 🛠️ Налаштування скрипта

### Змінити шлях проекту
Відредагуйте змінну `PROJECT_DIR` в `create_secure_backup.sh`:
```bash
PROJECT_DIR="/your/custom/path"
```

### Додати виключення файлів
Відредагуйте секцію виключень у скрипті:
```bash
# Додати нові шаблони виключень
-not -name "*.custom_extension"
-not -path "*/custom_folder/*"
```

### Змінити папку призначення
Відредагуйте змінну `BACKUP_DIR`:
```bash
BACKUP_DIR="/your/custom/backup/path"
```

## 📈 Автоматизація

### Створення регулярних бекапів
Додайте до crontab для щоденних бекапів:
```bash
# Редагувати crontab
crontab -e

# Додати рядок для щоденного бекапу о 2:00
0 2 * * * /home/Bot1/backups/create_secure_backup.sh >/dev/null 2>&1
```

### Очищення старих бекапів
Створіть скрипт очищення старих бекапів (зберігати останні 7):
```bash
cd /home/Bot1/backups
ls -t *.tar.gz | tail -n +8 | xargs rm -f
```

## 🔍 Перевірка цілісності

### Перевірка архіву
```bash
# Перевірити цілісність архіву
tar -tzf backup_file.tar.gz >/dev/null && echo "OK" || echo "CORRUPTED"

# Перевірити наявність ключових файлів
tar -tzf backup_file.tar.gz | grep -E "(src/|config/|requirements.txt)"
```

### Перевірка безпеки
```bash
# Переконатися, що конфіденційні файли відсутні
tar -tzf backup_file.tar.gz | grep -E "(credentials\.env$|service_account\.json|\.log$)" && echo "SECURITY ISSUE" || echo "SECURE"
```

## 📞 Підтримка

### Часті проблеми

**Проблема:** `Permission denied`  
**Рішення:** Переконайтеся, що скрипт має права на виконання: `chmod +x create_secure_backup.sh`

**Проблема:** Архів занадто великий  
**Рішення:** Перевірте, що всі великі файли (логи, venv) правильно виключені

**Проблема:** Відсутні файли після відновлення  
**Рішення:** Перевірте шляхи у скрипті та права доступу до файлів

### Логування
Скрипт автоматично логує всі операції. Для детальної діагностики запустіть:
```bash
bash -x ./create_secure_backup.sh
```

---

**Автор:** GitHub Copilot  
**Проект:** Bot1 Telegram Bot with Jira Integration  
**Репозиторій:** euromixtgbot/bot1  
**Версія документації:** 1.0  
**Дата останнього оновлення:** 2025-09-09
