#!/bin/bash

# =====================================
# BOT MONITORING CONTROL SCRIPT
# =====================================
# Зручний інтерфейс для управління моніторингом бота

BOT_DIR="/home/Bot1"
MONITOR_SCRIPT="$BOT_DIR/monitor_bot.sh"

# Кольори
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Функція показу меню
show_menu() {
    clear
    echo -e "${BLUE}╔══════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║        BOT MONITORING CONTROL        ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${YELLOW}1.${NC} Статус системи"
    echo -e "${YELLOW}2.${NC} Запустити моніторинг"
    echo -e "${YELLOW}3.${NC} Зупинити моніторинг"
    echo -e "${YELLOW}4.${NC} Перезапустити моніторинг"
    echo -e "${YELLOW}5.${NC} Перевірити бота зараз"
    echo -e "${YELLOW}6.${NC} Показати логи моніторингу"
    echo -e "${YELLOW}7.${NC} Показати логи systemd"
    echo -e "${YELLOW}8.${NC} Налаштувати автозапуск"
    echo -e "${YELLOW}9.${NC} Видалити моніторинг"
    echo -e "${RED}0.${NC} Вихід"
    echo ""
    echo -n "Оберіть дію (0-9): "
}

# Функція показу статусу
show_status() {
    echo -e "${BLUE}=== СТАТУС СИСТЕМИ МОНІТОРИНГУ ===${NC}"
    echo ""
    
    # Статус systemd сервісу
    if systemctl is-active --quiet bot-monitor.service; then
        echo -e "Systemd сервіс: ${GREEN}АКТИВНИЙ${NC}"
    else
        echo -e "Systemd сервіс: ${RED}НЕАКТИВНИЙ${NC}"
    fi
    
    if systemctl is-enabled --quiet bot-monitor.service 2>/dev/null; then
        echo -e "Автозапуск: ${GREEN}УВІМКНЕНО${NC}"
    else
        echo -e "Автозапуск: ${RED}ВИМКНЕНО${NC}"
    fi
    
    echo ""
    
    # Статус бота
    "$MONITOR_SCRIPT" status
    
    echo ""
    echo -e "${YELLOW}Натисніть Enter для продовження...${NC}"
    read
}

# Функція запуску моніторингу
start_monitoring() {
    echo -e "${YELLOW}🚀 Запуск моніторингу...${NC}"
    systemctl start bot-monitor.service
    sleep 2
    
    if systemctl is-active --quiet bot-monitor.service; then
        echo -e "${GREEN}✅ Моніторинг запущено успішно${NC}"
    else
        echo -e "${RED}❌ Помилка запуску моніторингу${NC}"
        echo -e "${YELLOW}Перевірте логи:${NC} journalctl -u bot-monitor"
    fi
    
    echo -e "${YELLOW}Натисніть Enter для продовження...${NC}"
    read
}

# Функція зупинки моніторингу
stop_monitoring() {
    echo -e "${YELLOW}🛑 Зупинка моніторингу...${NC}"
    systemctl stop bot-monitor.service
    sleep 2
    
    if ! systemctl is-active --quiet bot-monitor.service; then
        echo -e "${GREEN}✅ Моніторинг зупинено${NC}"
    else
        echo -e "${RED}❌ Помилка зупинки моніторингу${NC}"
    fi
    
    echo -e "${YELLOW}Натисніть Enter для продовження...${NC}"
    read
}

# Функція перезапуску моніторингу
restart_monitoring() {
    echo -e "${YELLOW}🔄 Перезапуск моніторингу...${NC}"
    systemctl restart bot-monitor.service
    sleep 3
    
    if systemctl is-active --quiet bot-monitor.service; then
        echo -e "${GREEN}✅ Моніторинг перезапущено успішно${NC}"
    else
        echo -e "${RED}❌ Помилка перезапуску моніторингу${NC}"
    fi
    
    echo -e "${YELLOW}Натисніть Enter для продовження...${NC}"
    read
}

# Функція перевірки бота
check_bot() {
    echo -e "${YELLOW}🔍 Перевірка стану бота...${NC}"
    "$MONITOR_SCRIPT" check
    echo ""
    echo -e "${YELLOW}Натисніть Enter для продовження...${NC}"
    read
}

# Функція показу логів моніторингу
show_monitor_logs() {
    echo -e "${BLUE}=== ЛОГИ МОНІТОРИНГУ (останні 50 записів) ===${NC}"
    if [[ -f "$BOT_DIR/logs/monitor.log" ]]; then
        tail -50 "$BOT_DIR/logs/monitor.log"
    else
        echo -e "${RED}Файл логів не знайдено${NC}"
    fi
    echo ""
    echo -e "${YELLOW}Натисніть Enter для продовження...${NC}"
    read
}

# Функція показу systemd логів
show_systemd_logs() {
    echo -e "${BLUE}=== SYSTEMD ЛОГИ (останні записи) ===${NC}"
    journalctl -u bot-monitor.service --no-pager -n 30
    echo ""
    echo -e "${YELLOW}Натисніть Enter для продовження...${NC}"
    read
}

# Функція налаштування автозапуску
setup_autostart() {
    echo -e "${YELLOW}🔧 Налаштування автозапуску...${NC}"
    
    if systemctl is-enabled --quiet bot-monitor.service 2>/dev/null; then
        echo "Автозапуск вже увімкнено. Вимкнути? (y/n): "
        read -r response
        if [[ "$response" =~ ^[Yy]$ ]]; then
            systemctl disable bot-monitor.service
            echo -e "${GREEN}✅ Автозапуск вимкнено${NC}"
        fi
    else
        echo "Автозапуск вимкнено. Увімкнути? (y/n): "
        read -r response
        if [[ "$response" =~ ^[Yy]$ ]]; then
            systemctl enable bot-monitor.service
            echo -e "${GREEN}✅ Автозапуск увімкнено${NC}"
        fi
    fi
    
    echo -e "${YELLOW}Натисніть Enter для продовження...${NC}"
    read
}

# Функція видалення моніторингу
remove_monitoring() {
    echo -e "${RED}⚠️ ВИДАЛЕННЯ СИСТЕМИ МОНІТОРИНГУ${NC}"
    echo "Це видалить весь моніторинг та systemd сервіс."
    echo -n "Ви впевнені? (y/N): "
    read -r response
    
    if [[ "$response" =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}🗑️ Видалення моніторингу...${NC}"
        
        # Зупинка та видалення сервісу
        systemctl stop bot-monitor.service 2>/dev/null
        systemctl disable bot-monitor.service 2>/dev/null
        rm -f /etc/systemd/system/bot-monitor.service
        systemctl daemon-reload
        
        echo -e "${GREEN}✅ Моніторинг видалено${NC}"
        echo -e "${BLUE}Файли скриптів залишені в $BOT_DIR${NC}"
    else
        echo -e "${GREEN}Скасовано${NC}"
    fi
    
    echo -e "${YELLOW}Натисніть Enter для продовження...${NC}"
    read
}

# Головний цикл
main() {
    while true; do
        show_menu
        read -r choice
        
        case $choice in
            1) show_status ;;
            2) start_monitoring ;;
            3) stop_monitoring ;;
            4) restart_monitoring ;;
            5) check_bot ;;
            6) show_monitor_logs ;;
            7) show_systemd_logs ;;
            8) setup_autostart ;;
            9) remove_monitoring ;;
            0) 
                echo -e "${GREEN}До побачення!${NC}"
                exit 0
                ;;
            *) 
                echo -e "${RED}Невірний вибір. Натисніть Enter...${NC}"
                read
                ;;
        esac
    done
}

# Перевірка прав
if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}❌ Цей скрипт повинен запускатися з правами root${NC}"
    echo "Використайте: sudo $0"
    exit 1
fi

# Запуск головного циклу
main
