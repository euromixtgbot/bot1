# 🔧 Виправлення Дублювання Логів
**Дата:** 2025-10-08  
**Час:** 19:03 UTC  
**Статус:** ✅ **ВИРІШЕНО**

---

## 📋 Проблема

### Симптоми:
1. ❌ **Кожен лог записується 2 рази** в `logs/bot.log`
2. ❌ **Повідомлення в Telegram дублюються** - "Оберіть сервіс:" показується двічі
3. ❌ **Всі записи з `__main__`, `src.*` модулів дублюються**

### Приклад з логів:
```
2025-10-08 18:57:02,336 - __main__ - INFO - Webhook сервер запущен на 0.0.0.0:9443
2025-10-08 18:57:02,336 - __main__ - INFO - Webhook сервер запущен на 0.0.0.0:9443  ← ДУБЛЮВАННЯ
2025-10-08 18:57:02,336 - __main__ - INFO - Запуск Telegram polling...
2025-10-08 18:57:02,336 - __main__ - INFO - Запуск Telegram polling...  ← ДУБЛЮВАННЯ
```

### Вплив на роботу:
- **Логи важко читати** - кожен рядок повторюється
- **Telegram повідомлення дублюються** - користувач бачить 2 однакові повідомлення
- **Збільшений розмір файлів логів** - файл росте вдвічі швидше

---

## 🔍 Діагностика

### Крок 1: Перевірка кількості процесів
```bash
ps aux | grep -E "python.*main.py" | grep -v grep | wc -l
# Результат: 1 ← Тільки 1 процес!
```

**Висновок**: Проблема НЕ в кількох процесах бота.

### Крок 2: Перевірка конфігурації logging
**Початкова конфігурація в `src/main.py`:**
```python
rotating_handler = RotatingFileHandler('logs/bot.log', ...)
logging.basicConfig(
    handlers=[
        logging.StreamHandler(sys.stdout),  # ← Handler #1
        rotating_handler                     # ← Handler #2
    ]
)
```

**Проблема**: 2 handlers додаються до root logger.

### Крок 3: Перевірка відкритих файлів
```bash
lsof | grep "bot.log"
# Результат:
python  9959  root  1w  REG  /home/Bot1/logs/bot.log  ← stdout перенаправлено
python  9959  root  2w  REG  /home/Bot1/logs/bot.log  ← stderr перенаправлено
python  9959  root  3w  REG  /home/Bot1/logs/bot.log  ← RotatingFileHandler
```

**Ключовий момент**: Файл bot.log відкрито **3 рази**!

### Крок 4: Аналіз скрипта запуску
**restart.sh, рядок 276:**
```bash
nohup python src/main.py > logs/bot_new.log 2>&1 &
                         ^^^^^^^^^^^^^^^^^^^^
                         stdout і stderr перенаправляються в файл
```

---

## 🎯 Корінна Причина

### Механізм дублювання:

1. **restart.sh** запускає бот з перенаправленням:
   ```bash
   python src/main.py > logs/bot_new.log 2>&1
   ```
   
2. **Python logging** додає 2 handlers:
   - `StreamHandler(sys.stdout)` - пише в stdout
   - `RotatingFileHandler('logs/bot.log')` - пише в файл

3. **sys.stdout перенаправлено** restart.sh в файл (bot_new.log → symlink → bot.log)

4. **Результат**: 
   - `RotatingFileHandler` пише в bot.log **один раз**
   - `StreamHandler(sys.stdout)` пише в перенаправлений stdout, який **теж пише в bot.log**
   - **Загалом: кожен log пишеться ДВІЧІ!**

### Діаграма:
```
logger.info("message")
    ↓
root_logger
    ├── StreamHandler(sys.stdout) → stdout → [перенаправлено restart.sh] → bot.log  (1)
    └── RotatingFileHandler → bot.log                                                (2)
                                                                                      ↓
                                                                            bot.log має 2 копії!
```

---

## ✅ Рішення

### Виправлення #1: Відключення propagation для jira_webhooks2

**src/jira_webhooks2.py:**
```python
logger = logging.getLogger(__name__)
logger.addHandler(webhook_rotating_handler)
logger.setLevel(logging.INFO)
logger.propagate = False  # ← Вимикаємо propagation до root logger
```

**Ефект**: Запобігає дублюванню логів з webhook модуля.

### Виправлення #2: Умовне додавання console handler

**src/main.py:**
```python
# Очищаємо всі існуючі handlers
root_logger = logging.getLogger()
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

# Налаштовуємо файловий handler
rotating_handler = RotatingFileHandler('logs/bot.log', ...)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
rotating_handler.setFormatter(formatter)

# Додаємо handlers до root logger
root_logger.setLevel(logging.INFO)
root_logger.addHandler(rotating_handler)

# ⚠️ КРИТИЧНО: Додаємо console handler ТІЛЬКИ якщо stdout НЕ перенаправлено в файл
if sys.stdout.isatty():
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
```

**Логіка:**
- `sys.stdout.isatty()` повертає `True` якщо stdout - терминал (interactive)
- `sys.stdout.isatty()` повертає `False` якщо stdout перенаправлено в файл
- Якщо stdout перенаправлено → НЕ додаємо `StreamHandler`
- Це запобігає дублюванню коли бот запускається через `nohup > file.log`

---

## 📊 Результати

### До виправлення:
```log
2025-10-08 18:57:02,336 - __main__ - INFO - Webhook сервер запущен на 0.0.0.0:9443
2025-10-08 18:57:02,336 - __main__ - INFO - Webhook сервер запущен на 0.0.0.0:9443
2025-10-08 18:57:02,336 - __main__ - INFO - Запуск Telegram polling...
2025-10-08 18:57:02,336 - __main__ - INFO - Запуск Telegram polling...
2025-10-08 18:57:02,372 - __main__ - INFO - ✅ Бот полностью запущен:
2025-10-08 18:57:02,372 - __main__ - INFO - ✅ Бот полностью запущен:
```

### Після виправлення:
```log
2025-10-08 19:02:29,852 - __main__ - INFO - Webhook сервер запущен на 0.0.0.0:9443
2025-10-08 19:02:29,852 - __main__ - INFO - Запуск Telegram polling для команд пользователей...
2025-10-08 19:02:29,896 - __main__ - INFO - ✅ Бот полностью запущен:
2025-10-08 19:02:29,896 - __main__ - INFO -   - Telegram polling: активен (обрабатывает команды пользователей)
2025-10-08 19:02:29,897 - __main__ - INFO -   - Jira webhook сервер: активен на 0.0.0.0:9443
```

**✅ Кожен рядок тепер записується тільки 1 раз!**

---

## 🔧 Технічні Деталі

### Змінені Файли:

#### 1. **src/main.py** (+5 рядків, -5 рядків)
```diff
- # Створюємо console handler
- console_handler = logging.StreamHandler(sys.stdout)
- console_handler.setFormatter(formatter)
-
- # Додаємо handlers до root logger
  root_logger.setLevel(logging.INFO)
- root_logger.addHandler(console_handler)
  root_logger.addHandler(rotating_handler)
+
+ # Додаємо console handler ТІЛЬКИ якщо stdout НЕ перенаправлено в файл
+ if sys.stdout.isatty():
+     console_handler = logging.StreamHandler(sys.stdout)
+     console_handler.setFormatter(formatter)
+     root_logger.addHandler(console_handler)
```

#### 2. **src/jira_webhooks2.py** (+1 рядок)
```diff
  logger = logging.getLogger(__name__)
  logger.addHandler(webhook_rotating_handler)
  logger.setLevel(logging.INFO)
+ logger.propagate = False  # Вимикаємо propagation до root logger
```

### Перевірка працездатності:
```bash
# Перезапуск бота
cd /home/Bot1
pkill -f "python.*main.py"
nohup python src/main.py > logs/bot_new.log 2>&1 &

# Перевірка логів
tail -n 20 /home/Bot1/logs/bot.log
# ✅ Кожен рядок тільки 1 раз!

# Перевірка процесу
ps aux | grep -E "python.*main.py" | grep -v grep
# root  10707  0.8  154456 70476  Ssl  19:03  0:00  python src/main.py
# ✅ Тільки 1 процес
```

---

## 📌 Вплив на Telegram

### Проблема з дублюванням повідомлень:

**Було:**
- Користувач натискає кнопку → handler викликається 1 раз
- Але **logger.info()** пише 2 рази → це НЕ впливало на Telegram повідомлення
- Дублювання "Оберіть сервіс:" було **НЕ через логування**

**Дублювання в Telegram** мало іншу причину:
- Можливо handler викликався двічі
- Або було 2 різні повідомлення від користувача
- Потрібна окрема діагностика

### Що виправлено:
✅ **Логи тепер чисті** - кожен рядок 1 раз  
✅ **Розмір файлів зменшився вдвічі**  
✅ **Легше читати і аналізувати логи**  

---

## 🎓 Висновки

### Ключові Уроки:

1. **`sys.stdout.isatty()`** - перевірка чи stdout перенаправлено
2. **Уникати додавання console handler** коли stdout вже перенаправлено в файл
3. **`logger.propagate = False`** - вимикає propagation до parent loggers
4. **`lsof | grep file.log`** - діагностика відкритих файлів
5. **Очищення handlers** перед конфігурацією - `root_logger.handlers[:].remove()`

### Best Practices:

```python
# ✅ ПРАВИЛЬНО: Перевірка перенаправлення stdout
if sys.stdout.isatty():
    console_handler = logging.StreamHandler(sys.stdout)
    root_logger.addHandler(console_handler)

# ✅ ПРАВИЛЬНО: Вимкнення propagation для модульного logger
logger = logging.getLogger(__name__)
logger.addHandler(custom_handler)
logger.propagate = False

# ❌ НЕПРАВИЛЬНО: Завжди додавати console handler
logging.basicConfig(handlers=[
    logging.StreamHandler(sys.stdout),  # ← дублювання якщо stdout перенаправлено
    RotatingFileHandler('bot.log')
])
```

---

## 🚀 Deployment

### Статус:
- ✅ Бот перезапущений (PID 10707)
- ✅ Дублювання логів усунено
- ✅ Всі handlers працюють правильно
- ✅ Синтаксичних помилок немає

### Логи:
```
2025-10-08 19:02:29,896 - __main__ - INFO - ✅ Бот полностью запущен:
2025-10-08 19:02:29,896 - __main__ - INFO -   - Telegram polling: активен
2025-10-08 19:02:29,897 - __main__ - INFO -   - Jira webhook сервер: активен на 0.0.0.0:9443
```

---

**Автор:** GitHub Copilot  
**Дата завершення:** 2025-10-08 19:03 UTC  
**Версія:** 1.0
