#!/bin/bash

# Скрипт для активации виртуальной среды и запуска бота

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Установка и запуск Telegram бота ===${NC}"

# Переход в директорию проекта
cd /home/Bot1

# Проверяем, существует ли виртуальная среда
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Создание виртуальной среды...${NC}"
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo -e "${RED}Ошибка создания виртуальной среды${NC}"
        exit 1
    fi
fi

# Активируем виртуальную среду
echo -e "${YELLOW}Активация виртуальной среды...${NC}"
source venv/bin/activate

# Обновляем pip
echo -e "${YELLOW}Обновление pip...${NC}"
pip install --upgrade pip

# Устанавливаем зависимости
echo -e "${YELLOW}Установка зависимостей...${NC}"
pip install -r requirements.txt

# Проверяем установку ключевых пакетов
echo -e "${YELLOW}Проверка установки ключевых пакетов...${NC}"
python -c "import telegram; print(f'python-telegram-bot: {telegram.__version__}')"
python -c "import httpx; print(f'httpx: {httpx.__version__}')"
python -c "import aiohttp; print(f'aiohttp: {aiohttp.__version__}')"

# Запускаем бота
echo -e "${GREEN}Запуск бота...${NC}"
cd src
python main.py
