#!/bin/bash

# Скрипт для активації віртуального середовища та запуску бота

# Переходимо в директорію бота
cd /home/Bot1

# Активуємо віртуальне середовище
source venv/bin/activate

# Встановлюємо PYTHONPATH
export PYTHONPATH=/home/Bot1:$PYTHONPATH

# Запускаємо бота
echo "🚀 Запускаємо Telegram бота..."
python src/main.py
