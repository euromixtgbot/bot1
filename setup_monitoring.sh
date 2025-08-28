#!/bin/bash

# =====================================
# SETUP BOT MONITORING SYSTEM
# =====================================
# Цей скрипт налаштовує систему моніторингу бота

BOT_DIR="/home/Bot1"
MONITOR_SCRIPT="$BOT_DIR/monitor_bot.sh"
SERVICE_FILE="$BOT_DIR/bot-monitor.service"
SYSTEMD_SERVICE="/etc/systemd/system/bot-monitor.service"

# Кольори
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== НАЛАШТУВАННЯ СИСТЕМИ МОНІТОРИНГУ БОТА ===${NC}"

# Перевіряємо права root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}❌ Цей скрипт повинен запускатися з правами root${NC}"
   echo "Використайте: sudo $0"
   exit 1
fi

# Перевіряємо наявність файлів
if [[ ! -f "$MONITOR_SCRIPT" ]]; then
    echo -e "${RED}❌ Файл $MONITOR_SCRIPT не знайдено${NC}"
    exit 1
fi

if [[ ! -f "$SERVICE_FILE" ]]; then
    echo -e "${RED}❌ Файл $SERVICE_FILE не знайдено${NC}"
    exit 1
fi

echo -e "${YELLOW}🔧 Налаштування прав доступу...${NC}"
chmod +x "$MONITOR_SCRIPT"

echo -e "${YELLOW}🔧 Копіювання systemd сервісу...${NC}"
cp "$SERVICE_FILE" "$SYSTEMD_SERVICE"

echo -e "${YELLOW}🔧 Перезавантаження systemd...${NC}"
systemctl daemon-reload

echo -e "${YELLOW}🔧 Увімкнення автозапуску сервісу...${NC}"
systemctl enable bot-monitor.service

echo -e "${YELLOW}🚀 Запуск сервісу моніторингу...${NC}"
systemctl start bot-monitor.service

# Чекаємо трохи і перевіряємо статус
sleep 3

if systemctl is-active --quiet bot-monitor.service; then
    echo -e "${GREEN}✅ Сервіс моніторингу успішно запущено!${NC}"
    echo ""
    echo -e "${BLUE}=== ІНФОРМАЦІЯ ===${NC}"
    echo -e "Сервіс: ${GREEN}bot-monitor.service${NC}"
    echo -e "Статус: ${GREEN}Активний${NC}"
    echo -e "Автозапуск: ${GREEN}Увімкнено${NC}"
    echo -e "Інтервал перевірки: ${YELLOW}15 хвилин${NC}"
    echo ""
    echo -e "${BLUE}=== КОРИСНІ КОМАНДИ ===${NC}"
    echo "Статус сервісу:           systemctl status bot-monitor"
    echo "Перезапуск сервісу:       systemctl restart bot-monitor"
    echo "Зупинка сервісу:          systemctl stop bot-monitor"
    echo "Логи сервісу:             journalctl -u bot-monitor -f"
    echo "Логи моніторингу:         tail -f $BOT_DIR/logs/monitor.log"
    echo "Статус бота:              $MONITOR_SCRIPT status"
    echo "Ручна перевірка:          $MONITOR_SCRIPT check"
else
    echo -e "${RED}❌ Помилка запуску сервісу моніторингу${NC}"
    echo -e "${YELLOW}Перевірте статус:${NC} systemctl status bot-monitor"
    echo -e "${YELLOW}Логи:${NC} journalctl -u bot-monitor"
    exit 1
fi

echo ""
echo -e "${GREEN}🎉 Налаштування завершено успішно!${NC}"
echo -e "${BLUE}Система моніторингу буде автоматично перевіряти стан бота кожні 15 хвилин.${NC}"
