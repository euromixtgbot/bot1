# 🌐 НАЛАШТУВАННЯ ДОМЕННОГО ІМЕНІ ТА SSL (ОПЦІОНАЛЬНО)

## 📋 Коли це потрібно:

- Використання webhook замість polling
- Професійний вигляд з власним доменом
- Підвищена безпека з SSL сертифікатами
- Інтеграція з зовнішніми сервісами

## 🎯 Варіанти налаштування:

### Варіант 1: Без домену (поточний)
✅ **Переваги:** Простота, швидкість  
❌ **Недоліки:** Polling, більше навантаження

### Варіант 2: З доменом та SSL
✅ **Переваги:** Webhook, менше навантаження, професійність  
❌ **Недоліки:** Потрібен домен, додаткові налаштування

---

## 🔧 Налаштування домену та SSL

### Крок 1: Реєстрація домену
```bash
# Приклад доменів для бота:
# - mycompany-bot.com
# - bot.mycompany.com
# - telegram.mycompany.com
```

### Крок 2: Налаштування DNS
```bash
# A запис для домену
bot.mycompany.com.  IN  A  YOUR_SERVER_IP

# Перевірка DNS
nslookup bot.mycompany.com
dig bot.mycompany.com
```

### Крок 3: Встановлення Nginx
```bash
# Встановлення Nginx
sudo apt update
sudo apt install nginx -y

# Запуск та автозапуск
sudo systemctl start nginx
sudo systemctl enable nginx

# Перевірка статусу
sudo systemctl status nginx
```

### Крок 4: Конфігурація Nginx
```bash
# Створення конфігурації
sudo nano /etc/nginx/sites-available/telegram-bot
```

**Вміст файлу конфігурації:**
```nginx
server {
    listen 80;
    server_name bot.mycompany.com;

    # Перенаправлення на HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name bot.mycompany.com;

    # SSL сертифікати (будуть створені пізніше)
    ssl_certificate /etc/letsencrypt/live/bot.mycompany.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/bot.mycompany.com/privkey.pem;

    # SSL налаштування
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;

    # Webhook endpoint
    location /webhook {
        proxy_pass http://127.0.0.1:8443;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Здоров'я перевірка
    location /health {
        proxy_pass http://127.0.0.1:8443;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Основна сторінка (опціонально)
    location / {
        return 200 "Telegram Bot is running";
        add_header Content-Type text/plain;
    }
}
```

### Крок 5: Активація конфігурації
```bash
# Створення символічного посилання
sudo ln -s /etc/nginx/sites-available/telegram-bot /etc/nginx/sites-enabled/

# Видалення стандартної конфігурації
sudo rm /etc/nginx/sites-enabled/default

# Перевірка конфігурації
sudo nginx -t

# Перезапуск Nginx
sudo systemctl restart nginx
```

### Крок 6: Встановлення Let's Encrypt SSL
```bash
# Встановлення Certbot
sudo apt install certbot python3-certbot-nginx -y

# Отримання SSL сертифіката
sudo certbot --nginx -d bot.mycompany.com

# Автоматичне оновлення сертифікатів
sudo crontab -e

# Додати рядок:
0 12 * * * /usr/bin/certbot renew --quiet
```

### Крок 7: Налаштування webhook в боті
```bash
# Редагування конфігурації бота
nano /home/Bot1/config/credentials.env
```

**Додайте webhook налаштування:**
```env
# WEBHOOK CONFIGURATION
WEBHOOK_URL=https://bot.mycompany.com/webhook
WEBHOOK_HOST=127.0.0.1
WEBHOOK_PORT=8443
WEBHOOK_SECRET_KEY=your_secret_key_here
```

### Крок 8: Модифікація коду бота для webhook
```bash
# Створення файлу webhook конфігурації
nano /home/Bot1/src/webhook_config.py
```

**Вміст файлу:**
```python
# webhook_config.py
import os
from telegram.ext import Application
from config.config import *

def setup_webhook(application: Application) -> None:
    """Налаштування webhook для бота"""
    if WEBHOOK_URL:
        # Встановлення webhook
        application.run_webhook(
            listen=WEBHOOK_HOST,
            port=WEBHOOK_PORT,
            webhook_url=WEBHOOK_URL,
            secret_token=WEBHOOK_SECRET_KEY,
            cert=SSL_CERT_PATH if SSL_CERT_PATH else None,
            key=SSL_KEY_PATH if SSL_KEY_PATH else None,
        )
    else:
        # Використання polling (поточний режим)
        application.run_polling()
```

### Крок 9: Оновлення main.py
```bash
# Редагування основного файлу
nano /home/Bot1/src/main.py
```

**Додайте в кінець main.py:**
```python
# Перед application.run_polling() додайте:
if __name__ == "__main__":
    from webhook_config import setup_webhook
    
    # Вибір між webhook та polling
    if WEBHOOK_URL:
        logger.info("🌐 Запуск з webhook режимом")
        setup_webhook(application)
    else:
        logger.info("🔄 Запуск з polling режимом")
        application.run_polling()
```

### Крок 10: Налаштування firewall
```bash
# Дозвіл HTTP/HTTPS
sudo ufw allow 80
sudo ufw allow 443

# Дозвіл webhook порту (локально)
sudo ufw allow from 127.0.0.1 to any port 8443

# Перевірка правил
sudo ufw status
```

---

## 🧪 Тестування webhook

### Перевірка SSL сертифіката
```bash
# Перевірка SSL
curl -I https://bot.mycompany.com/health

# Детальна перевірка SSL
openssl s_client -connect bot.mycompany.com:443 -servername bot.mycompany.com
```

### Встановлення webhook в Telegram
```bash
# Встановлення webhook через API
curl -X POST "https://api.telegram.org/bot<YOUR_TOKEN>/setWebhook" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://bot.mycompany.com/webhook"}'

# Перевірка webhook
curl "https://api.telegram.org/bot<YOUR_TOKEN>/getWebhookInfo"
```

### Перевірка логів
```bash
# Логи Nginx
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log

# Логи бота
tail -f /home/Bot1/logs/bot_*.log

# Системні логи
sudo journalctl -u telegram-bot.service -f
```

---

## 🔧 Troubleshooting

### Проблема 1: SSL сертифікат не створюється
```bash
# Перевірка DNS
nslookup bot.mycompany.com

# Ручне створення сертифіката
sudo certbot certonly --standalone -d bot.mycompany.com

# Перевірка портів
sudo netstat -tlnp | grep :80
sudo netstat -tlnp | grep :443
```

### Проблема 2: Webhook не працює
```bash
# Перевірка webhook статусу
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"

# Видалення webhook (повернення до polling)
curl -X POST "https://api.telegram.org/bot<TOKEN>/deleteWebhook"

# Перевірка доступності endpoint
curl -X POST https://bot.mycompany.com/webhook
```

### Проблема 3: Nginx помилки
```bash
# Перевірка конфігурації
sudo nginx -t

# Перевірка логів помилок
sudo tail -f /var/log/nginx/error.log

# Перезапуск сервісів
sudo systemctl restart nginx
sudo systemctl restart telegram-bot.service
```

---

## 📊 Порівняння режимів

| Характеристика | Polling | Webhook |
|----------------|---------|---------|
| **Складність налаштування** | Проста | Складна |
| **Потребує домен** | Ні | Так |
| **Потребує SSL** | Ні | Так |
| **Навантаження на сервер** | Вище | Нижче |
| **Затримка повідомлень** | 1-2 сек | Миттєво |
| **Надійність** | Висока | Висока |
| **Масштабованість** | Обмежена | Краща |

---

## 📝 Рекомендації

### Для невеликих проектів:
✅ **Залишайтеся з polling** - простіше та надійніше

### Для продуктивних систем:
✅ **Переходьте на webhook** - краща продуктивність

### Перехід з polling на webhook:
1. Налаштуйте домен та SSL
2. Оновіть конфігурацію бота
3. Встановіть webhook через API
4. Протестуйте функціональність
5. Моніторьте роботу

**💡 Поточна система відмінно працює з polling. Webhook - це оптимізація для майбутнього.**
