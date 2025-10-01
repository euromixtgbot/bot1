#!/bin/bash
# Скрипт для архівації старих логів у .gz формат
# Стискає логи старші N днів та видаляє дуже старі архіви

LOGS_DIR="/home/Bot1/logs"
ARCHIVE_DIR="/home/Bot1/logs/archive"
DAYS_TO_COMPRESS=7
DAYS_TO_DELETE=30

echo "=== Log Archiving Script ==="
echo "Date: $(date)"
echo "Compressing logs older than ${DAYS_TO_COMPRESS} days..."
echo ""

# Створити директорію для архівів
mkdir -p "$ARCHIVE_DIR"

# Підрахунок файлів для архівації
FILES_TO_COMPRESS=$(find "$LOGS_DIR" -maxdepth 1 -name "*.log.[0-9]*" -mtime +$DAYS_TO_COMPRESS -type f | wc -l)
echo "Found $FILES_TO_COMPRESS backup files to compress"

# Знайти та стиснути логи старші N днів
if [ $FILES_TO_COMPRESS -gt 0 ]; then
    find "$LOGS_DIR" -maxdepth 1 -name "*.log.[0-9]*" -mtime +$DAYS_TO_COMPRESS -type f | while read file; do
        basename=$(basename "$file")
        datestamp=$(date -r "$file" +"%Y%m%d")
        gzip -c "$file" > "$ARCHIVE_DIR/${basename}_${datestamp}.gz" 2>/dev/null
        if [ $? -eq 0 ]; then
            rm "$file"
            echo "  ✓ Archived: $basename → ${basename}_${datestamp}.gz"
        else
            echo "  ✗ Failed: $basename"
        fi
    done
else
    echo "  No files to compress"
fi

echo ""
echo "Deleting archives older than ${DAYS_TO_DELETE} days..."

# Видалити архіви старші 30 днів
OLD_ARCHIVES=$(find "$ARCHIVE_DIR" -name "*.gz" -mtime +$DAYS_TO_DELETE -type f | wc -l)
if [ $OLD_ARCHIVES -gt 0 ]; then
    find "$ARCHIVE_DIR" -name "*.gz" -mtime +$DAYS_TO_DELETE -type f -delete
    echo "  ✓ Deleted $OLD_ARCHIVES old archives"
else
    echo "  No old archives to delete"
fi

# Статистика
echo ""
echo "=== Summary ==="
ARCHIVE_SIZE=$(du -sh "$ARCHIVE_DIR" 2>/dev/null | cut -f1)
ARCHIVE_COUNT=$(find "$ARCHIVE_DIR" -name "*.gz" -type f 2>/dev/null | wc -l)
LOGS_SIZE=$(du -sh "$LOGS_DIR" | cut -f1)
echo "Archive directory size: ${ARCHIVE_SIZE:-0}"
echo "Archive files count: $ARCHIVE_COUNT"
echo "Total logs directory size: $LOGS_SIZE"
echo ""
echo "✅ Archiving completed successfully"
