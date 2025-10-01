#!/bin/bash
# Скрипт для очищення старих log файлів
# Видаляє застарілі файли з timestamp у назві

LOGS_DIR="/home/Bot1/logs"
DAYS_TO_KEEP=7

echo "=== Log Cleanup Script ==="
echo "Date: $(date)"
echo "Cleaning logs older than ${DAYS_TO_KEEP} days..."
echo ""

# Підрахунок перед очищенням
OLD_COUNT=$(find "$LOGS_DIR" -maxdepth 1 \( -name "bot_001_*.log" -o -name "webhook_001_*.log" \) -mtime +$DAYS_TO_KEEP | wc -l)
echo "Found $OLD_COUNT old log files to delete"

# Видалити bot_001_*.log файли старші N днів
find "$LOGS_DIR" -maxdepth 1 -name "bot_001_*.log" -mtime +$DAYS_TO_KEEP -type f -delete
echo "✓ Deleted old bot_001_*.log files"

# Видалити webhook_001_*.log файли старші N днів
find "$LOGS_DIR" -maxdepth 1 -name "webhook_001_*.log" -mtime +$DAYS_TO_KEEP -type f -delete
echo "✓ Deleted old webhook_001_*.log files"

# Видалити .log.N файли старші 30 днів (backup файли від RotatingFileHandler)
OLD_BACKUP_COUNT=$(find "$LOGS_DIR" -maxdepth 1 -name "*.log.[0-9]*" -mtime +30 | wc -l)
if [ $OLD_BACKUP_COUNT -gt 0 ]; then
    find "$LOGS_DIR" -maxdepth 1 -name "*.log.[0-9]*" -mtime +30 -type f -delete
    echo "✓ Deleted $OLD_BACKUP_COUNT old backup files (.log.N)"
fi

# Статистика після очищення
echo ""
echo "=== Summary ==="
CURRENT_SIZE=$(du -sh "$LOGS_DIR" | cut -f1)
CURRENT_COUNT=$(find "$LOGS_DIR" -maxdepth 1 -name "*.log*" -type f | wc -l)
echo "Current logs directory size: $CURRENT_SIZE"
echo "Current log files count: $CURRENT_COUNT"
echo ""
echo "✅ Cleanup completed successfully"
