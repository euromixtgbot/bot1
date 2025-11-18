# Zabbix Monitoring - Інструкція з Налаштування

**Дата створення:** 18 листопада 2025  
**Версія Zabbix:** 7.0.21  
**Сервер:** bot02 (157.180.46.236)

---

## 📋 Зміст

1. [Встановлення](#встановлення)
2. [Конфігурація](#конфігурація)
3. [Параметри Моніторингу Бота](#параметри-моніторингу-бота)
4. [Підключення до Zabbix Server](#підключення-до-zabbix-server)
5. [Тестування](#тестування)
6. [Усунення Неполадок](#усунення-неполадок)

---

## ✅ Встановлення

### Крок 1: Додавання Репозиторію Zabbix

```bash
# Завантаження та встановлення репозиторію
wget https://repo.zabbix.com/zabbix/7.0/ubuntu/pool/main/z/zabbix-release/zabbix-release_latest_7.0+ubuntu24.04_all.deb
sudo dpkg -i zabbix-release_latest_7.0+ubuntu24.04_all.deb
sudo apt update
```

### Крок 2: Встановлення Zabbix Agent 2

```bash
# Встановлення агента та плагінів
sudo apt install -y zabbix-agent2 zabbix-agent2-plugin-*
```

**Встановлені компоненти:**
- `zabbix-agent2` - основний агент моніторингу
- `zabbix-agent2-plugin-mongodb` - плагін для MongoDB
- `zabbix-agent2-plugin-postgresql` - плагін для PostgreSQL
- `zabbix-agent2-plugin-mssql` - плагін для MS SQL
- `zabbix-agent2-plugin-ember-plus` - плагін для Ember+

---

## ⚙️ Конфігурація

### Основний файл конфігурації

**Шлях:** `/etc/zabbix/zabbix_agent2.conf`

```bash
# Backup оригінального файлу
sudo cp /etc/zabbix/zabbix_agent2.conf /etc/zabbix/zabbix_agent2.conf.backup
```

### Ключові параметри

```conf
# Системні параметри
PidFile=/run/zabbix/zabbix_agent2.pid
LogFile=/var/log/zabbix/zabbix_agent2.log
LogFileSize=10

# Конфігурація сервера
Server=127.0.0.1,157.180.46.236          # IP адреси Zabbix серверів
ServerActive=127.0.0.1:10051             # Адреса для активних перевірок
Hostname=bot02                            # Унікальне ім'я хоста

# Налаштування продуктивності
Timeout=30
Include=/etc/zabbix/zabbix_agent2.d/*.conf

# Плагіни
Plugins.SystemRun.LogRemoteCommands=1
```

**Важливо:** 
- `Server` - список IP адрес, з яких дозволено підключення
- `ServerActive` - адреса для активного моніторингу
- `Hostname` - має збігатися з назвою хоста в Zabbix Server

---

## 🤖 Параметри Моніторингу Бота

### Спеціальні UserParameter для Telegram Bot

```conf
# Статус сервісів
UserParameter=bot.status,systemctl is-active telegram-bot
UserParameter=bot.monitor.status,systemctl is-active bot-monitor
UserParameter=nginx.status,systemctl is-active nginx

# Процес бота
UserParameter=bot.pid,pgrep -f "python.*main.py" | head -1
UserParameter=bot.memory,ps aux | grep "python.*main.py" | grep -v grep | awk '{print $6}'
UserParameter=bot.cpu,ps aux | grep "python.*main.py" | grep -v grep | awk '{print $3}'
UserParameter=bot.uptime,ps -p $(pgrep -f "python.*main.py" | head -1) -o etime= 2>/dev/null | tr -d ' '

# Статистика бота
UserParameter=bot.users.count,ls /home/Bot1/user_states/*.json 2>/dev/null | wc -l
UserParameter=bot.log.errors,grep -c "ERROR" /home/Bot1/logs/bot.log 2>/dev/null || echo 0
UserParameter=bot.log.size,du -b /home/Bot1/logs/bot.log 2>/dev/null | awk '{print $1}'

# Використання диску
UserParameter=disk.bot.usage,du -sb /home/Bot1 | awk '{print $1}'
```

### Опис Параметрів

| Параметр | Опис | Тип значення | Приклад |
|----------|------|--------------|---------|
| `bot.status` | Статус сервісу telegram-bot | string | `active` |
| `bot.monitor.status` | Статус сервісу bot-monitor | string | `active` |
| `nginx.status` | Статус Nginx | string | `active` |
| `bot.pid` | PID процесу бота | integer | `183908` |
| `bot.memory` | Використання пам'яті (KB) | integer | `72272` |
| `bot.cpu` | Використання CPU (%) | float | `0.1` |
| `bot.uptime` | Час роботи процесу | string | `1-02:30:15` |
| `bot.users.count` | Кількість активних користувачів | integer | `3` |
| `bot.log.errors` | Кількість помилок у логах | integer | `0` |
| `bot.log.size` | Розмір лог-файлу (bytes) | integer | `1234567` |
| `disk.bot.usage` | Використання диску Bot1 (bytes) | integer | `172032000` |

---

## 🔗 Підключення до Zabbix Server

### Крок 1: Запуск та Активація Сервісу

```bash
# Перезапуск агента
sudo systemctl restart zabbix-agent2

# Увімкнення автозапуску
sudo systemctl enable zabbix-agent2

# Перевірка статусу
sudo systemctl status zabbix-agent2
```

### Крок 2: Налаштування Firewall (якщо потрібно)

```bash
# Відкрити порт 10050 для Zabbix Server
sudo ufw allow from <ZABBIX_SERVER_IP> to any port 10050
sudo ufw reload
```

### Крок 3: Додавання Хоста в Zabbix Server

1. **Авторизуйтесь у Zabbix Web Interface**
2. **Configuration → Hosts → Create host**
3. **Заповніть поля:**
   - **Host name:** `bot02`
   - **Visible name:** `Telegram Bot Server (bot02)`
   - **Groups:** `Linux servers`, `Telegram Bots`
   - **Interfaces:**
     - **Type:** Agent
     - **IP address:** `157.180.46.236`
     - **Port:** `10050`

4. **Templates:**
   - `Linux by Zabbix agent`
   - `Zabbix agent active`

5. **Macros (опціонально):**
   ```
   {$BOT_DIR} = /home/Bot1
   {$BOT_LOG} = /home/Bot1/logs/bot.log
   ```

### Крок 4: Створення Custom Items у Zabbix

**Configuration → Hosts → bot02 → Items → Create item**

**Приклад Item для статусу бота:**
- **Name:** Bot Service Status
- **Type:** Zabbix agent
- **Key:** `bot.status`
- **Type of information:** Character
- **Update interval:** 30s
- **Applications:** Bot Monitoring

**Приклад Item для кількості користувачів:**
- **Name:** Bot Active Users Count
- **Type:** Zabbix agent
- **Key:** `bot.users.count`
- **Type of information:** Numeric (unsigned)
- **Update interval:** 60s

**Приклад Item для пам'яті:**
- **Name:** Bot Memory Usage (KB)
- **Type:** Zabbix agent
- **Key:** `bot.memory`
- **Type of information:** Numeric (unsigned)
- **Update interval:** 30s
- **Units:** KB

---

## 🧪 Тестування

### Локальне Тестування Параметрів

```bash
# Тестування окремих параметрів
zabbix_agent2 -t bot.status
zabbix_agent2 -t bot.monitor.status
zabbix_agent2 -t bot.users.count
zabbix_agent2 -t bot.memory
zabbix_agent2 -t bot.cpu
zabbix_agent2 -t bot.uptime
zabbix_agent2 -t bot.log.errors
zabbix_agent2 -t nginx.status
```

**Очікувані результати:**
```
bot.status                    [s|active]
bot.monitor.status            [s|active]
bot.users.count               [s|3]
bot.memory                    [s|72272]
bot.cpu                       [s|0.1]
bot.uptime                    [s|1-02:30:15]
bot.log.errors                [s|0]
nginx.status                  [s|active]
```

### Перевірка з Zabbix Server

```bash
# На Zabbix Server виконати:
zabbix_get -s 157.180.46.236 -k bot.status
zabbix_get -s 157.180.46.236 -k bot.users.count
zabbix_get -s 157.180.46.236 -k bot.memory
```

### Перевірка Логів

```bash
# Перегляд логів агента
sudo tail -f /var/log/zabbix/zabbix_agent2.log

# Перевірка помилок
sudo journalctl -u zabbix-agent2 -n 50
```

---

## 🔧 Усунення Неполадок

### Проблема: Агент не запускається

```bash
# Перевірка конфігурації
sudo zabbix_agent2 -t agent.ping

# Перевірка синтаксису конфігурації
sudo zabbix_agent2 -T

# Перегляд детальних логів
sudo journalctl -u zabbix-agent2 -f
```

### Проблема: Параметри повертають порожні значення

```bash
# Перевірка прав доступу
ls -la /home/Bot1/user_states/
ls -la /home/Bot1/logs/

# Тестування команди вручну
pgrep -f "python.*main.py"
ps aux | grep "python.*main.py" | grep -v grep
```

### Проблема: Zabbix Server не може підключитися

```bash
# Перевірка firewall
sudo ufw status
sudo iptables -L | grep 10050

# Перевірка прослуховування порту
sudo netstat -tulpn | grep 10050

# Перевірка конфігурації Server
grep "^Server=" /etc/zabbix/zabbix_agent2.conf
```

### Проблема: UserParameter не працює

```bash
# Перевірка безпосередньо
bash -c "systemctl is-active telegram-bot"
bash -c "ls /home/Bot1/user_states/*.json 2>/dev/null | wc -l"

# Перевірка через агента
zabbix_agent2 -t bot.status
zabbix_agent2 -t bot.users.count
```

---

## 📊 Рекомендовані Triggers

### Критичні

```
{bot02:bot.status.str(active)}<>1
Опис: Bot service is down
Severity: High
```

```
{bot02:bot.monitor.status.str(active)}<>1
Опис: Bot monitor service is down
Severity: High
```

### Попередження

```
{bot02:bot.memory.last()}>100000
Опис: Bot memory usage is high (>100MB)
Severity: Warning
```

```
{bot02:bot.log.errors.last()}>10
Опис: Too many errors in bot log
Severity: Warning
```

### Інформаційні

```
{bot02:bot.users.count.change()}<>0
Опис: Number of active users changed
Severity: Information
```

---

## 📈 Dashboard Items

Рекомендовані графіки для Dashboard:

1. **Bot Memory Usage** - графік використання пам'яті
2. **Bot CPU Usage** - графік використання CPU
3. **Active Users Count** - кількість активних користувачів
4. **Log File Size** - розмір лог-файлу
5. **Service Status** - статус сервісів (bot, monitor, nginx)

---

## 🔄 Оновлення Конфігурації

```bash
# Після внесення змін у конфігурацію
sudo systemctl restart zabbix-agent2

# Перевірка статусу
sudo systemctl status zabbix-agent2

# Тестування нових параметрів
zabbix_agent2 -t <new_parameter>
```

---

## 📝 Файли та Шляхи

| Компонент | Шлях |
|-----------|------|
| Конфігурація | `/etc/zabbix/zabbix_agent2.conf` |
| Додаткові конфігурації | `/etc/zabbix/zabbix_agent2.d/*.conf` |
| Логи | `/var/log/zabbix/zabbix_agent2.log` |
| PID файл | `/run/zabbix/zabbix_agent2.pid` |
| Systemd сервіс | `/usr/lib/systemd/system/zabbix-agent2.service` |
| Backup конфігурації | `/etc/zabbix/zabbix_agent2.conf.backup` |

---

## 🔗 Корисні Посилання

- [Zabbix 7.0 Documentation](https://www.zabbix.com/documentation/7.0/)
- [Zabbix Agent 2 Configuration](https://www.zabbix.com/documentation/7.0/manual/appendix/config/zabbix_agent2)
- [User Parameters](https://www.zabbix.com/documentation/7.0/manual/config/items/userparameters)

---

## ✅ Статус Встановлення

**Дата встановлення:** 18.11.2025  
**Версія агента:** 7.0.21  
**Статус:** ✅ Активний  
**Автозапуск:** ✅ Увімкнено  
**Hostname:** bot02  
**IP:** 157.180.46.236  
**Порт:** 10050  

**Встановлені параметри моніторингу:**
- ✅ Bot service status
- ✅ Bot monitor status
- ✅ Nginx status
- ✅ Bot memory/CPU usage
- ✅ Active users count
- ✅ Error logs count
- ✅ Disk usage

---

**© 2025 EuroMix Telegram Bot Project**

