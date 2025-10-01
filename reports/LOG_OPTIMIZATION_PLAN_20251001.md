# План оптимізації системи логування

**Дата створення:** 01.10.2025  
**Автор:** GitHub Copilot  
**Статус:** 📋 Planning Phase  
**Пріоритет:** 🔴 High (bot.log = 35MB, загальний розмір = 71MB)

---

## 📋 Зміст
1. [Поточний стан](#поточний-стан)
2. [Виявлені проблеми](#виявлені-проблеми)
3. [Цілі оптимізації](#цілі-оптимізації)
4. [План реалізації](#план-реалізації)
5. [Деталі кожного етапу](#деталі-кожного-етапу)
6. [Конфігурація](#конфігурація)
7. [Метрики успіху](#метрики-успіху)
8. [Ризики та обмеження](#ризики-та-обмеження)

---

## 📊 Поточний стан

### Статистика логів (станом на 01.10.2025):
```bash
Загальний розмір директорії logs/:  71 MB
Кількість .log файлів:               63 файли
Розмір bot.log (основний):           35 MB ⚠️
Розмір webhook.log:                  16 KB
Розмір conflict_errors.log:          355 B
```

### Структура логування:

#### 1. **main.py (bot.log)**
```python
# Поточна конфігурація:
rotating_handler = RotatingFileHandler(
    log_filename='logs/bot_001_YYYYMMDD_HHMMSS.log',
    maxBytes=5*1024*1024,  # 5MB
    backupCount=10,        # 10 файлів
    encoding='utf-8'
)
```
**Проблема:** a. Створюється новий файл при кожному перезапуску, старі не видаляються! b. нумерація файлів не працює. скрізь номер 01 - помилково. c. 

#### 2. **jira_webhooks2.py (webhook logs)**
```python
# Поточна конфігурація:
webhook_rotating_handler = RotatingFileHandler(
    webhook_log_filename='logs/webhook_001_YYYYMMDD_HHMMSS.log',
    maxBytes=5*1024*1024,  # 5MB
    backupCount=10,        # 10 файлів
    encoding='utf-8'
)
```
**Проблема:** Теж самий шаблон - нові файли без очищення старих!

#### 3. **Інші модулі**
- `attachment_processor.py` - використовує root logger
- `user_state_service.py` - використовує root logger
- `handlers.py` - використовує root logger
- `services.py` - використовує root logger (множинні instance)
- `user_management_service.py` - використовує root logger

**Проблема:** Всі пишуть у bot.log без контролю розміру!

---

## 🔍 Виявлені проблеми

### Критичні:

#### 1. **Нескінченне накопичення логів** 🔴
**Симптоми:**
- 63 log файли в директорії
- bot.log = 35 MB (перевищує ліміт 5MB)
- Загальний розмір = 71 MB

**Причина:**
```python
# При кожному перезапуску:
log_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_filename = f'logs/bot_001_{log_timestamp}.log'
```
Створюється НОВИЙ файл з timestamp, але він НЕ підпадає під RotatingFileHandler rotation!

**Наслідки:**
- Заповнення диска
- Складність пошуку логів
- Неможливість автоматичного моніторингу

#### 2. **bot.log не ротується** 🔴
**Симптоми:**
- bot.log = 35 MB (має бути max 5MB)
- Немає bot.log.1, bot.log.2 файлів

**Причина:**
RotatingFileHandler налаштований на інший файл (`bot_001_*.log`), а не на `bot.log`!

**Наслідки:**
- Повільне читання логів
- Ризик втрати даних
- Проблеми з парсингом

#### 3. **Відсутність архівації** 🟠
**Симптоми:**
- Всі логи в текстовому форматі
- Немає .gz архівів
- Старі логи займають місце

**Причина:**
Не налаштована автоматична компресія старих логів

**Наслідки:**
- Неефективне використання диска
- Складність backup

#### 4. **Невідповідні рівні логування** 🟡
**Симптоми:**
```python
# Занадто багато INFO логів:
2025-10-01 15:27:34 - httpx - INFO - HTTP Request: POST https://...
2025-10-01 15:27:44 - httpx - INFO - HTTP Request: POST https://...
# Повторюється кожні 10 секунд!
```

**Причина:**
- httpx логує кожен HTTP request на рівні INFO
- Telegram API polling логує кожні 10 секунд
- Немає фільтрації шумних логерів

**Наслідки:**
- Заповнення логів шумом
- Складність знаходження реальних проблем
- Швидке зростання розміру

#### 5. **Дублювання логів** 🟡
**Симптоми:**
- Логи пишуться і в stdout, і в файл
- При перезапуску - нові файли

**Причина:**
```python
handlers=[
    logging.StreamHandler(sys.stdout),  # Дублювання в консоль
    rotating_handler
]
```

**Наслідки:**
- Надлишкові дані в systemd journal
- Зайва навантаження на I/O

---

## 🎯 Цілі оптимізації

### Першочергові цілі:

1. **Зменшити розмір логів на 80%**
   - З 71 MB до ~15 MB
   - bot.log максимум 10 MB

2. **Автоматична ротація**
   - Створювати bot.log.1, bot.log.2, ... bot.log.10
   - При досягненні 10MB - ротація
   - Зберігати останні 10 файлів

3. **Автоматична архівація**
   - Стискати логи старші 7 днів
   - Формат: bot.log.DD_MM_YYYY.gz
   - Видаляти архіви старші 30 днів

4. **Оптимізація рівнів**
   - httpx: WARNING замість INFO
   - telegram: WARNING замість INFO
   - Основні модулі: INFO (як є)

5. **Структурування логів**
   - bot.log - основний (Telegram bot)
   - webhook.log - Jira webhooks
   - error.log - тільки ERROR та CRITICAL
   - debug.log - DEBUG (якщо потрібен)

### Додаткові цілі:

6. **Моніторинг розміру**
   - Попередження при досягненні 50 MB
   - Автоматичне очищення при 100 MB

7. **Структуровані логи**
   - JSON формат для критичних подій
   - Можливість парсингу

8. **Централізоване налаштування**
   - Один файл конфігурації для всіх модулів
   - Можливість змінити рівні без перезапуску

---

## 📅 План реалізації

### Фаза 1: Базова оптимізація (30-40 хвилин)
**Пріоритет:** 🔴 Критичний

#### Крок 1.1: Виправлення основного логування (10 хв)
**Файл:** `src/main.py`

**Зміни:**
```python
# ❌ ДО (поточний код):
log_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_filename = f'logs/bot_001_{log_timestamp}.log'
rotating_handler = RotatingFileHandler(
    log_filename,
    maxBytes=5*1024*1024,
    backupCount=10,
)

# ✅ ПІСЛЯ:
rotating_handler = RotatingFileHandler(
    'logs/bot.log',  # Фіксована назва!
    maxBytes=10*1024*1024,  # 10MB
    backupCount=10,         # bot.log.1 ... bot.log.10
    encoding='utf-8'
)
```

**Результат:**
- bot.log автоматично ротується
- Створюються bot.log.1, bot.log.2, ... bot.log.10
- Старі файли bot_001_*.log можна видалити

#### Крок 1.2: Виправлення webhook логування (10 хв)
**Файл:** `src/jira_webhooks2.py`

**Зміни:**
```python
# ❌ ДО:
webhook_log_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
webhook_log_filename = f'logs/webhook_001_{webhook_log_timestamp}.log'
webhook_rotating_handler = RotatingFileHandler(
    webhook_log_filename,
    maxBytes=5*1024*1024,
    backupCount=10,
)

# ✅ ПІСЛЯ:
webhook_rotating_handler = RotatingFileHandler(
    'logs/webhook.log',  # Фіксована назва!
    maxBytes=5*1024*1024,  # 5MB
    backupCount=5,         # webhook.log.1 ... webhook.log.5
    encoding='utf-8'
)
```

#### Крок 1.3: Зменшення шуму від httpx та telegram (10 хв)
**Файл:** `src/main.py`

**Додати після basicConfig:**
```python
# Зменшуємо рівень логування для шумних бібліотек
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)
logging.getLogger('telegram.ext').setLevel(logging.WARNING)
logging.getLogger('aiohttp.access').setLevel(logging.WARNING)
logging.getLogger('aiohttp.server').setLevel(logging.WARNING)
```

**Результат:**
- Зменшення логів на ~70%
- Тільки важливі події від HTTP/Telegram

#### Крок 1.4: Очищення старих логів (100 хв)
**Створити:** `scripts/cleanup_old_logs.sh`

```bash
#!/bin/bash
# Очищення старих log файлів

LOGS_DIR="/home/Bot1/logs"
DAYS_TO_KEEP=7

# Видалити .log файли старші 7 днів (крім bot.log, webhook.log)
find "$LOGS_DIR" -name "bot_001_*.log" -mtime +$DAYS_TO_KEEP -delete
find "$LOGS_DIR" -name "webhook_001_*.log" -mtime +$DAYS_TO_KEEP -delete

# Видалити .log.N файли старші 30 днів
find "$LOGS_DIR" -name "*.log.[0-9]*" -mtime +30 -delete

echo "Old logs cleaned up successfully"
```

**Додати в crontab:**
```bash
# Щоденне очищення о 2:00 AM
0 2 * * * /home/Bot1/scripts/cleanup_old_logs.sh >> /home/Bot1/logs/cleanup.log 2>&1
```

---

### Фаза 2: Архівація та компресія (20-30 хвилин)
**Пріоритет:** 🟠 Високий

#### Крок 2.1: Скрипт архівації (15 хв)
**Створити:** `scripts/archive_logs.sh`

```bash
#!/bin/bash
# Архівація старих логів у .gz формат

LOGS_DIR="/home/Bot1/logs"
ARCHIVE_DIR="/home/Bot1/logs/archive"
DAYS_TO_COMPRESS=7

# Створити директорію для архівів
mkdir -p "$ARCHIVE_DIR"

# Знайти та стиснути логи старші 7 днів
find "$LOGS_DIR" -maxdepth 1 -name "*.log.[0-9]*" -mtime +$DAYS_TO_COMPRESS -type f | while read file; do
    basename=$(basename "$file")
    gzip -c "$file" > "$ARCHIVE_DIR/${basename}.gz"
    rm "$file"
    echo "Archived: $basename"
done

# Видалити архіви старші 30 днів
find "$ARCHIVE_DIR" -name "*.gz" -mtime +30 -delete

echo "Log archiving completed"
```

**Додати в crontab:**
```bash
# Щоденна архівація о 3:00 AM
0 3 * * * /home/Bot1/scripts/archive_logs.sh >> /home/Bot1/logs/archive.log 2>&1
```

#### Крок 2.2: Тестування архівації (5 хв)
```bash
# Ручний запуск для тесту
bash scripts/archive_logs.sh

# Перевірка результатів
ls -lh logs/archive/
```

#### Крок 2.3: Моніторинг розміру (10 хв)
**Створити:** `scripts/monitor_logs_size.sh`

```bash
#!/bin/bash
# Моніторинг розміру логів з попередженням

LOGS_DIR="/home/Bot1/logs"
WARNING_SIZE_MB=50
CRITICAL_SIZE_MB=100

# Перевірка розміру
current_size_kb=$(du -s "$LOGS_DIR" | cut -f1)
current_size_mb=$((current_size_kb / 1024))

echo "Current logs size: ${current_size_mb}MB"

if [ $current_size_mb -gt $CRITICAL_SIZE_MB ]; then
    echo "🔴 CRITICAL: Logs size exceeded ${CRITICAL_SIZE_MB}MB!"
    # Можна додати Telegram notification
    # curl -s -X POST https://api.telegram.org/bot.../sendMessage ...
elif [ $current_size_mb -gt $WARNING_SIZE_MB ]; then
    echo "🟠 WARNING: Logs size exceeded ${WARNING_SIZE_MB}MB"
fi
```

**Додати в crontab:**
```bash
# Перевірка кожні 6 годин
0 */6 * * * /home/Bot1/scripts/monitor_logs_size.sh >> /home/Bot1/logs/monitor.log 2>&1
```

---

### Фаза 3: Структурування логів (20-30 хвилин)
**Пріоритет:** 🟡 Середній

#### Крок 3.1: Окремий error.log (15 хв)
**Файл:** `src/main.py`

**Додати error handler:**
```python
# Окремий файл для ERROR та CRITICAL
error_handler = RotatingFileHandler(
    'logs/error.log',
    maxBytes=5*1024*1024,  # 5MB
    backupCount=5,
    encoding='utf-8'
)
error_handler.setLevel(logging.ERROR)
error_formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
)
error_handler.setFormatter(error_formatter)

# Додати до root logger
logging.getLogger().addHandler(error_handler)
```

**Результат:**
- Всі помилки дублюються в error.log
- Легко знайти критичні проблеми

#### Крок 3.2: Debug режим (за потреби) (10 хв)
**Файл:** `config/config.py`

```python
# Додати налаштування
DEBUG_MODE: bool = os.getenv("DEBUG_MODE", "false").lower() == "true"
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
```

**Файл:** `src/main.py`

```python
# Використовувати з config
from config.config import DEBUG_MODE, LOG_LEVEL

# Налаштувати рівень
log_level = getattr(logging, LOG_LEVEL, logging.INFO)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=log_level,
    handlers=[...]
)

# Debug файл (якщо увімкнений)
if DEBUG_MODE:
    debug_handler = RotatingFileHandler(
        'logs/debug.log',
        maxBytes=10*1024*1024,
        backupCount=3,
        encoding='utf-8'
    )
    debug_handler.setLevel(logging.DEBUG)
    logging.getLogger().addHandler(debug_handler)
```

#### Крок 3.3: Централізоване налаштування (5 хв)
**Створити:** `src/logging_config.py`

```python
"""
Централізована конфігурація логування для всього проекту.
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional

# Створення директорії для логів
os.makedirs('logs', exist_ok=True)

def setup_logging(
    log_level: str = "INFO",
    debug_mode: bool = False,
    max_bytes: int = 10*1024*1024,  # 10MB
    backup_count: int = 10
) -> None:
    """
    Налаштування системи логування для всього проекту.
    
    Args:
        log_level: Рівень логування (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        debug_mode: Чи увімкнений режим debug
        max_bytes: Максимальний розмір файлу логу
        backup_count: Кількість backup файлів
    """
    # Основний handler (bot.log)
    main_handler = RotatingFileHandler(
        'logs/bot.log',
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    main_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    main_handler.setFormatter(main_formatter)
    
    # Error handler (error.log)
    error_handler = RotatingFileHandler(
        'logs/error.log',
        maxBytes=5*1024*1024,  # 5MB
        backupCount=5,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
    )
    error_handler.setFormatter(error_formatter)
    
    # Базова конфігурація
    handlers = [main_handler, error_handler]
    
    # Debug handler (якщо увімкнений)
    if debug_mode:
        debug_handler = RotatingFileHandler(
            'logs/debug.log',
            maxBytes=10*1024*1024,
            backupCount=3,
            encoding='utf-8'
        )
        debug_handler.setLevel(logging.DEBUG)
        debug_handler.setFormatter(main_formatter)
        handlers.append(debug_handler)
    
    # Конфігурація root logger
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        handlers=handlers
    )
    
    # Зменшення шуму від сторонніх бібліотек
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('telegram').setLevel(logging.WARNING)
    logging.getLogger('telegram.ext').setLevel(logging.WARNING)
    logging.getLogger('aiohttp.access').setLevel(logging.WARNING)
    logging.getLogger('aiohttp.server').setLevel(logging.WARNING)
    
    logger = logging.getLogger(__name__)
    logger.info(f"Logging initialized: level={log_level}, debug={debug_mode}")
    logger.info(f"Log rotation: max_bytes={max_bytes/1024/1024:.1f}MB, backup_count={backup_count}")


def get_module_logger(name: str) -> logging.Logger:
    """
    Отримати logger для модуля з правильними налаштуваннями.
    
    Args:
        name: Ім'я модуля (зазвичай __name__)
        
    Returns:
        logging.Logger: Налаштований logger
    """
    return logging.getLogger(name)
```

**Використання в модулях:**
```python
# Замість:
import logging
logger = logging.getLogger(__name__)

# Використовувати:
from src.logging_config import get_module_logger
logger = get_module_logger(__name__)
```

---

### Фаза 4: Покращення та автоматизація (30-40 хвилин)
**Пріоритет:** 🟢 Низький (optional)

#### Крок 4.1: JSON структуровані логи (15 хв)
**Для критичних подій:**
```python
import json

class JSONFormatter(logging.Formatter):
    """Formatter для JSON логів."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Додаткові поля для ERROR
        if record.levelno >= logging.ERROR:
            log_data["exc_info"] = self.formatException(record.exc_info) if record.exc_info else None
        
        return json.dumps(log_data, ensure_ascii=False)

# Використання:
json_handler = RotatingFileHandler('logs/structured.log', ...)
json_handler.setFormatter(JSONFormatter())
```

#### Крок 4.2: Logrotate конфігурація (10 хв)
**Створити:** `/etc/logrotate.d/telegram-bot`

```
/home/Bot1/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    missingok
    create 0644 root root
    postrotate
        # Можна додати команду для reload bot (якщо потрібно)
    endscript
}
```

#### Крок 4.3: Dashboard для логів (15 хв)
**Створити:** `scripts/log_dashboard.sh`

```bash
#!/bin/bash
# Простий dashboard для перегляду статистики логів

echo "=== Telegram Bot Logs Dashboard ==="
echo ""
echo "📊 Загальна статистика:"
echo "  Розмір logs/: $(du -sh /home/Bot1/logs | cut -f1)"
echo "  Кількість файлів: $(find /home/Bot1/logs -name '*.log' | wc -l)"
echo ""
echo "📁 Основні файли:"
ls -lh /home/Bot1/logs/*.log 2>/dev/null | awk '{print "  " $9 ": " $5}'
echo ""
echo "🔴 ERROR рівень (останні 10):"
tail -100 /home/Bot1/logs/bot.log | grep ERROR | tail -10
echo ""
echo "📈 Статистика рівнів (останні 1000 рядків):"
tail -1000 /home/Bot1/logs/bot.log | grep -oP '(?<=- )\w+(?= -)' | sort | uniq -c | sort -rn
```

---

## ⚙️ Конфігурація

### Параметри в `credentials.env`:

```bash
# === Logging Configuration ===

# Рівень логування (DEBUG, INFO, WARNING, ERROR, CRITICAL)
LOG_LEVEL=INFO

# Debug режим (створює debug.log з детальними логами)
DEBUG_MODE=false

# Ротація логів
LOG_MAX_SIZE_MB=10          # Максимальний розмір файлу (MB)
LOG_BACKUP_COUNT=10         # Кількість backup файлів
LOG_WEBHOOK_MAX_SIZE_MB=5   # Розмір для webhook логів
LOG_WEBHOOK_BACKUP_COUNT=5  # Backup для webhook

# Архівація
LOG_ARCHIVE_DAYS=7          # Архівувати логи старші N днів
LOG_DELETE_DAYS=30          # Видаляти архіви старші N днів

# Моніторинг
LOG_WARNING_SIZE_MB=50      # Попередження при розмірі
LOG_CRITICAL_SIZE_MB=100    # Критичний розмір
```

### Рівні логування по модулях:

| Модуль | Рекомендований рівень | Причина |
|--------|----------------------|---------|
| `httpx` | WARNING | Занадто багато INFO про кожен HTTP запит |
| `telegram` | WARNING | Логує кожен getUpdates (кожні 10 сек) |
| `telegram.ext` | WARNING | Внутрішні події telegram bot |
| `aiohttp.access` | WARNING | Логує кожен webhook запит |
| `aiohttp.server` | WARNING | Внутрішні події aiohttp |
| `src.main` | INFO | Основна логіка бота |
| `src.handlers` | INFO | Обробка команд користувачів |
| `src.services` | INFO | Взаємодія з Jira |
| `src.jira_webhooks2` | INFO | Обробка webhook від Jira |

---

## 📈 Метрики успіху

### Цільові показники:

| Метрика | Поточне значення | Цільове значення | Покращення |
|---------|------------------|------------------|------------|
| Розмір logs/ | 71 MB | < 20 MB | -72% |
| bot.log | 35 MB | < 10 MB | -71% |
| Кількість файлів | 63 | < 20 | -68% |
| Рівень шуму | Високий | Низький | -70% INFO логів |
| Швидкість зростання | ~10 MB/день | < 2 MB/день | -80% |

### KPI після впровадження:

1. ✅ **bot.log автоматично ротується** при досягненні 10MB
2. ✅ **Зберігаються тільки останні 10 backup** файлів
3. ✅ **Логи старші 7 днів архівуються** у .gz формат
4. ✅ **Архіви старші 30 днів видаляються** автоматично
5. ✅ **ERROR логи окремо** в error.log для швидкого доступу
6. ✅ **Шум від httpx/telegram зменшений** на 70%
7. ✅ **Моніторинг розміру** з попередженнями

---

## ⚠️ Ризики та обмеження

### Ризики:

1. **Втрата важливих логів**
   - **Ризик:** Автоматичне видалення може видалити потрібні дані
   - **Мітігація:** 
     - Збільшити backup_count до 10
     - Архівувати перед видаленням
     - Зберігати архіви 30 днів

2. **Проблеми з ротацією під час роботи**
   - **Ризик:** RotatingFileHandler може конфліктувати при одночасному доступі
   - **Мітігація:**
     - Python RotatingFileHandler thread-safe
     - Тестування на dev середовищі

3. **Зміна формату логів**
   - **Ризик:** Існуючі скрипти парсингу можуть зламатись
   - **Мітігація:**
     - Зберігати стандартний формат
     - JSON тільки для structured.log (окремо)

### Обмеження:

1. **Мінімальний розмір ротації:** 1MB (рекомендується 5-10MB)
2. **Кількість backup файлів:** Обмежена диском (рекомендується 5-20)
3. **Архівація:** Вимагає додаткове CPU для gzip
4. **Cron jobs:** Потребують root доступу для налаштування

---

## 🔄 Rollback план

Якщо щось піде не так:

### Крок 1: Зупинити бота
```bash
pkill -f "python.*main.py"
```

### Крок 2: Відновити старі файли
```bash
cd /home/Bot1
git checkout src/main.py
git checkout src/jira_webhooks2.py
```

### Крок 3: Перезапустити бота
```bash
./restart.sh
```

### Крок 4: Видалити cron jobs (якщо додані)
```bash
crontab -e
# Видалити рядки з cleanup_old_logs.sh та archive_logs.sh
```

---

## 📝 Чеклист виконання

### Фаза 1: Базова оптимізація ✅
- [ ] Виправити bot.log rotation (src/main.py)
- [ ] Виправити webhook.log rotation (src/jira_webhooks2.py)
- [ ] Зменшити шум від httpx/telegram
- [ ] Створити cleanup_old_logs.sh
- [ ] Додати cleanup в crontab
- [ ] Тестування: перезапустити бота
- [ ] Тестування: перевірити bot.log.1, bot.log.2
- [ ] Видалити старі bot_001_*.log файли

### Фаза 2: Архівація ✅
- [ ] Створити scripts/archive_logs.sh
- [ ] Створити logs/archive/ директорію
- [ ] Додати archive в crontab
- [ ] Тестування: запустити archive_logs.sh вручну
- [ ] Створити monitor_logs_size.sh
- [ ] Додати monitor в crontab

### Фаза 3: Структурування ✅
- [ ] Додати error.log handler
- [ ] Додати DEBUG_MODE в config
- [ ] Створити src/logging_config.py
- [ ] Оновити всі модулі для використання logging_config
- [ ] Тестування: перевірити error.log

### Фаза 4: Покращення (Optional) ✅
- [ ] JSON formatter для structured.log
- [ ] Logrotate конфігурація
- [ ] Log dashboard скрипт
- [ ] Документація для команди

---

## 📚 Додаткові ресурси

### Документація:
- Python logging: https://docs.python.org/3/library/logging.html
- RotatingFileHandler: https://docs.python.org/3/library/logging.handlers.html#rotatingfilehandler
- Logrotate: https://linux.die.net/man/8/logrotate

### Best Practices:
- Python Logging Best Practices: https://docs.python-guide.org/writing/logging/
- Log Rotation: https://www.loggly.com/ultimate-guide/managing-python-logs/

### Інструменти:
- `tail -f logs/bot.log` - real-time моніторинг
- `grep ERROR logs/bot.log` - пошук помилок
- `du -sh logs/` - розмір директорії
- `zcat logs/archive/bot.log.gz` - читання архівів

---

## 🎯 Наступні кроки

1. **Обговорення плану** з командою
2. **Вибір фаз** для реалізації (рекомендується Фаза 1 + Фаза 2)
3. **Резервне копіювання** поточних логів
4. **Покрокова реалізація** з тестуванням
5. **Моніторинг** протягом тижня після впровадження
6. **Коригування** параметрів за потреби

---

**Автор:** GitHub Copilot  
**Дата створення:** 01.10.2025  
**Версія документа:** 1.0  
**Статус:** 📋 Ready for Implementation  
**Очікуваний час виконання:** 80-140 хвилин (залежно від фаз)
