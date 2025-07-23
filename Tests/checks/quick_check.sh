#!/bin/bash

# Скрипт для быстрой проверки проекта на ошибки и запуска

echo "🔍 Быстрая проверка проекта..."

# Переход в директорию проекта
cd /home/Bot1

# Проверка синтаксиса Python файлов
echo "📝 Проверка синтаксиса основных файлов..."

python3 -m py_compile src/main.py 2>/dev/null && echo "✅ main.py - OK" || echo "❌ main.py - ОШИБКА"
python3 -m py_compile src/handlers.py 2>/dev/null && echo "✅ handlers.py - OK" || echo "❌ handlers.py - ОШИБКА" 
python3 -m py_compile src/services.py 2>/dev/null && echo "✅ services.py - OK" || echo "❌ services.py - ОШИБКА"
python3 -m py_compile src/jira_webhooks2.py 2>/dev/null && echo "✅ jira_webhooks2.py - OK" || echo "❌ jira_webhooks2.py - ОШИБКА"
python3 -m py_compile config/config.py 2>/dev/null && echo "✅ config.py - OK" || echo "❌ config.py - ОШИБКА"

echo ""
echo "📋 Проверка конфигурации..."

# Проверка наличия основных файлов конфигурации
[ -f "config/credentials.env" ] && echo "✅ credentials.env найден" || echo "❌ credentials.env отсутствует"
[ -f "config/service_account.json" ] && echo "✅ service_account.json найден" || echo "❌ service_account.json отсутствует"
[ -f "requirements.txt" ] && echo "✅ requirements.txt найден" || echo "❌ requirements.txt отсутствует"

echo ""
echo "🔧 Проверка переменных окружения..."

# Активируем виртуальную среду если она есть
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "✅ Виртуальная среда активирована"
fi

# Проверка основных переменных
python3 -c "
import os
from dotenv import load_dotenv
load_dotenv('config/credentials.env')

vars_to_check = [
    'TELEGRAM_BOT_TOKEN',
    'JIRA_DOMAIN', 
    'JIRA_EMAIL',
    'JIRA_API_TOKEN',
    'JIRA_PROJECT_KEY'
]

for var in vars_to_check:
    value = os.getenv(var)
    if value:
        print(f'✅ {var} установлен')
    else:
        print(f'❌ {var} не установлен')
" 2>/dev/null || echo "⚠️  Не удалось проверить переменные (возможно, не установлен python-dotenv)"

echo ""
echo "📦 Проверка основных пакетов..."

# Проверка наличия основных пакетов
python3 -c "import telegram; print('✅ python-telegram-bot установлен')" 2>/dev/null || echo "❌ python-telegram-bot не установлен"
python3 -c "import httpx; print('✅ httpx установлен')" 2>/dev/null || echo "❌ httpx не установлен"
python3 -c "import aiohttp; print('✅ aiohttp установлен')" 2>/dev/null || echo "❌ aiohttp не установлен"

echo ""
echo "🚀 Готов к запуску? (y/n)"
read -r response

if [[ "$response" =~ ^[Yy]$ ]]; then
    echo "▶️  Запускаем бота..."
    cd src
    python3 main.py
else
    echo "🛑 Запуск отменен"
fi
