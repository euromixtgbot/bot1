#!/bin/bash

# Скрипт для корректной установки всех зависимостей

echo "🔧 Настройка окружения для Telegram бота..."

# Переход в директорию проекта
cd /home/Bot1

# Создание виртуальной среды если её нет
if [ ! -d "venv" ]; then
    echo "📦 Создание виртуальной среды..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "❌ Ошибка создания виртуальной среды"
        exit 1
    fi
fi

# Активация виртуальной среды
echo "🔀 Активация виртуальной среды..."
source venv/bin/activate

# Обновление pip
echo "⬆️  Обновление pip..."
pip install --upgrade pip

# Установка зависимостей из requirements_fixed.txt если он есть
if [ -f "requirements_fixed.txt" ]; then
    echo "📋 Установка зависимостей из requirements_fixed.txt..."
    pip install -r requirements_fixed.txt
elif [ -f "requirements.txt" ]; then
    echo "📋 Установка зависимостей из requirements.txt..."
    pip install -r requirements.txt
else
    echo "⚠️  Файл requirements не найден, устанавливаю основные пакеты..."
    pip install python-telegram-bot==21.3 httpx==0.27.0 aiohttp==3.9.5 python-dotenv==1.0.1 pyyaml==6.0.1 gspread==6.1.2 google-auth==2.29.0 requests==2.31.0
fi

# Проверка установки основных пакетов
echo ""
echo "🔍 Проверка установленных пакетов..."

python -c "
import sys
print(f'Python версия: {sys.version}')
print()

packages = [
    ('telegram', 'python-telegram-bot'),
    ('httpx', 'httpx'),
    ('aiohttp', 'aiohttp'), 
    ('dotenv', 'python-dotenv'),
    ('yaml', 'pyyaml'),
    ('gspread', 'gspread'),
    ('google.auth', 'google-auth'),
    ('requests', 'requests')
]

for module_name, package_name in packages:
    try:
        module = __import__(module_name)
        version = getattr(module, '__version__', 'unknown')
        print(f'✅ {package_name}: {version}')
    except ImportError:
        print(f'❌ {package_name}: не установлен')
    except Exception as e:
        print(f'⚠️  {package_name}: {e}')
"

echo ""
echo "✅ Установка завершена! Виртуальная среда готова к использованию."
echo ""
echo "Для активации виртуальной среды используйте:"
echo "source venv/bin/activate"
echo ""
echo "Для запуска бота используйте:"
echo "./quick_check.sh"
