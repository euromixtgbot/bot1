#!/bin/bash
# Скрипт для моніторингу розміру логів з попередженням

LOGS_DIR="/home/Bot1/logs"
WARNING_SIZE_MB=50
CRITICAL_SIZE_MB=100

echo "=== Log Size Monitoring ==="
echo "Date: $(date)"
echo ""

# Перевірка розміру
current_size_kb=$(du -s "$LOGS_DIR" | cut -f1)
current_size_mb=$((current_size_kb / 1024))

echo "📊 Current logs directory size: ${current_size_mb}MB"
echo "   Warning threshold: ${WARNING_SIZE_MB}MB"
echo "   Critical threshold: ${CRITICAL_SIZE_MB}MB"
echo ""

# Статистика файлів
log_count=$(find "$LOGS_DIR" -maxdepth 1 -name "*.log" -type f | wc -l)
backup_count=$(find "$LOGS_DIR" -maxdepth 1 -name "*.log.[0-9]*" -type f | wc -l)
old_count=$(find "$LOGS_DIR" -maxdepth 1 \( -name "bot_001_*.log" -o -name "webhook_001_*.log" \) -type f | wc -l)

echo "📁 File statistics:"
echo "   Active log files: $log_count"
echo "   Backup files (.log.N): $backup_count"
echo "   Old timestamp logs: $old_count"
echo ""

# Топ-5 найбільших файлів
echo "📈 Top 5 largest files:"
find "$LOGS_DIR" -maxdepth 1 -type f -exec ls -lh {} \; | sort -k5 -hr | head -5 | awk '{print "   " $9 ": " $5}'
echo ""

# Перевірка порогів
if [ $current_size_mb -gt $CRITICAL_SIZE_MB ]; then
    echo "🔴 CRITICAL: Logs size exceeded ${CRITICAL_SIZE_MB}MB!"
    echo "   Action required: Run cleanup_old_logs.sh or archive_logs.sh"
    exit 2
elif [ $current_size_mb -gt $WARNING_SIZE_MB ]; then
    echo "🟠 WARNING: Logs size exceeded ${WARNING_SIZE_MB}MB"
    echo "   Consider running cleanup or archiving soon"
    exit 1
else
    echo "✅ OK: Logs size is within acceptable limits"
    exit 0
fi
