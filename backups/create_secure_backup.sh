#!/bin/bash

# Скрипт для створення безпечного бекапу без логів та конфіденційної інформації
# Дата: 2025-09-08

set -e

# Колори для виводу
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функція для логування
log() {
    echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# Конфігурація
PROJECT_DIR="/home/Bot1"
BACKUP_DIR="/home/Bot1/backups"
DATE=$(date '+%Y%m%d_%H%M%S')
BACKUP_NAME="Bot1_secure_backup_${DATE}"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"

log "Початок створення безпечного бекапу..."

# Створюємо папку для бекапів якщо не існує
mkdir -p "$BACKUP_DIR"

# Створюємо тимчасову папку для підготовки бекапу
TEMP_DIR=$(mktemp -d)
TEMP_BACKUP_DIR="${TEMP_DIR}/${BACKUP_NAME}"
mkdir -p "$TEMP_BACKUP_DIR"

log "Тимчасова папка: $TEMP_DIR"

# Копіюємо основні файли проекту
info "Копіювання основних файлів..."

# Корневі файли проекту
cp "$PROJECT_DIR"/*.md "$TEMP_BACKUP_DIR/" 2>/dev/null || true
cp "$PROJECT_DIR"/*.sh "$TEMP_BACKUP_DIR/" 2>/dev/null || true
cp "$PROJECT_DIR"/*.toml "$TEMP_BACKUP_DIR/" 2>/dev/null || true
cp "$PROJECT_DIR"/*.json "$TEMP_BACKUP_DIR/" 2>/dev/null || true
cp "$PROJECT_DIR"/*.txt "$TEMP_BACKUP_DIR/" 2>/dev/null || true
cp "$PROJECT_DIR"/*.service "$TEMP_BACKUP_DIR/" 2>/dev/null || true
cp "$PROJECT_DIR"/.gitignore "$TEMP_BACKUP_DIR/" 2>/dev/null || true

# Копіюємо папки з кодом
log "Копіювання папок з кодом..."
cp -r "$PROJECT_DIR/src" "$TEMP_BACKUP_DIR/" 2>/dev/null || true
cp -r "$PROJECT_DIR/utils" "$TEMP_BACKUP_DIR/" 2>/dev/null || true
cp -r "$PROJECT_DIR/Tests" "$TEMP_BACKUP_DIR/" 2>/dev/null || true
cp -r "$PROJECT_DIR/deployment" "$TEMP_BACKUP_DIR/" 2>/dev/null || true

# Копіюємо scripts та monitoring БЕЗ логів
log "Копіювання scripts та monitoring (без логів)..."
if [ -d "$PROJECT_DIR/scripts" ]; then
    mkdir -p "$TEMP_BACKUP_DIR/scripts"
    find "$PROJECT_DIR/scripts" -type f -not -path "*/logs/*" -not -name "*.log" -not -name "*.pid" | while read file; do
        rel_path=${file#$PROJECT_DIR/scripts/}
        mkdir -p "$TEMP_BACKUP_DIR/scripts/$(dirname "$rel_path")"
        cp "$file" "$TEMP_BACKUP_DIR/scripts/$rel_path"
    done
fi

if [ -d "$PROJECT_DIR/monitoring" ]; then
    mkdir -p "$TEMP_BACKUP_DIR/monitoring"
    find "$PROJECT_DIR/monitoring" -type f -not -path "*/logs/*" -not -name "*.log" -not -name "*.pid" | while read file; do
        rel_path=${file#$PROJECT_DIR/monitoring/}
        mkdir -p "$TEMP_BACKUP_DIR/monitoring/$(dirname "$rel_path")"
        cp "$file" "$TEMP_BACKUP_DIR/monitoring/$rel_path"
    done
fi

# Копіюємо конфігурацію БЕЗ конфіденційних файлів
log "Копіювання конфігурації (без конфіденційних даних)..."
mkdir -p "$TEMP_BACKUP_DIR/config"
cp "$PROJECT_DIR/config/__init__.py" "$TEMP_BACKUP_DIR/config/" 2>/dev/null || true
cp "$PROJECT_DIR/config/config.py" "$TEMP_BACKUP_DIR/config/" 2>/dev/null || true
cp "$PROJECT_DIR/config/credentials.env.template" "$TEMP_BACKUP_DIR/config/" 2>/dev/null || true
cp "$PROJECT_DIR/config/fields_mapping.yaml" "$TEMP_BACKUP_DIR/config/" 2>/dev/null || true

# Копіюємо звіти
log "Копіювання звітів..."
cp -r "$PROJECT_DIR/reports" "$TEMP_BACKUP_DIR/" 2>/dev/null || true

# Копіюємо VS Code налаштування якщо є
if [ -d "$PROJECT_DIR/.vscode" ]; then
    log "Копіювання VS Code налаштувань..."
    cp -r "$PROJECT_DIR/.vscode" "$TEMP_BACKUP_DIR/" 2>/dev/null || true
fi

# Створюємо файл з інформацією про бекап
log "Створення інформаційного файлу..."
cat > "$TEMP_BACKUP_DIR/BACKUP_INFO.md" << EOF
# 🗂️ Інформація про безпечний бекап

**Дата створення:** $(date '+%Y-%m-%d %H:%M:%S')  
**Тип бекапу:** Безпечний (без логів та конфіденційних даних)  
**Версія:** $BACKUP_NAME

## 📋 Що включено в бекап

### ✅ Включені файли та папки:
- \`src/\` - Вихідний код проекту
- \`utils/\` - Утилітарні модулі
- \`scripts/\` - Скрипти автоматизації
- \`Tests/\` - Тестові файли
- \`monitoring/\` - Система моніторингу
- \`deployment/\` - Файли розгортання
- \`reports/\` - Технічні звіти
- \`config/\` - Конфігурація (БЕЗ конфіденційних даних)
- \`.vscode/\` - Налаштування VS Code
- Корневі конфігураційні файли (\`*.md\`, \`*.toml\`, \`*.json\`, \`*.txt\`, \`*.sh\`)

### ❌ Виключені файли та папки:
- \`logs/\` - Логи системи (можуть містити конфіденційну інформацію)
- \`scripts/logs/\` - Логи скриптів
- \`monitoring/logs/\` - Логи моніторингу
- \`*.log\` - Всі лог файли
- \`*.pid\` - PID файли процесів
- \`venv/\` - Віртуальне середовище Python
- \`user_states/\` - Стани користувачів
- \`data/\` - Робочі дані
- \`backups/\` - Попередні бекапи
- \`.git/\` - Git репозиторій
- \`config/credentials.env\` - Конфіденційні дані
- \`config/service_account.json\` - Ключі сервісного акаунту
- \`config/field_values.json\` - Значення полів (можуть містити конфіденційну інформацію)
- \`__pycache__/\` - Кеш Python

## 🔧 Відновлення з бекапу

1. Розпакуйте архів:
   \`\`\`bash
   tar -xzf $BACKUP_NAME.tar.gz
   \`\`\`

2. Відновіть конфіденційні файли з шаблонів:
   \`\`\`bash
   cp config/credentials.env.template config/credentials.env
   # Заповніть необхідні токени та ключі
   \`\`\`

3. Створіть віртуальне середовище:
   \`\`\`bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   \`\`\`

4. Створіть необхідні папки:
   \`\`\`bash
   mkdir -p logs data user_states
   \`\`\`

## 🛡️ Безпека

Цей бекап НЕ містить:
- Токени та API ключі
- Паролі та секретні дані
- Логи з можливою конфіденційною інформацією
- Стани користувачів
- Робочі дані

EOF

# Створюємо список файлів у бекапі
log "Створення списку файлів..."
find "$TEMP_BACKUP_DIR" -type f | sed "s|$TEMP_BACKUP_DIR/||" | sort > "$TEMP_BACKUP_DIR/FILES_LIST.txt"

# Рахуємо статистику
TOTAL_FILES=$(find "$TEMP_BACKUP_DIR" -type f | wc -l)
TOTAL_SIZE=$(du -sh "$TEMP_BACKUP_DIR" | cut -f1)

info "Всього файлів у бекапі: $TOTAL_FILES"
info "Розмір бекапу: $TOTAL_SIZE"

# Створюємо архів
log "Створення архіву..."
cd "$TEMP_DIR"
tar -czf "$BACKUP_PATH" "$BACKUP_NAME"

# Видаляємо тимчасову папку
rm -rf "$TEMP_DIR"

# Перевіряємо створений архів
if [ -f "$BACKUP_PATH" ]; then
    ARCHIVE_SIZE=$(ls -lh "$BACKUP_PATH" | awk '{print $5}')
    log "✅ Безпечний бекап успішно створено!"
    echo ""
    echo "📁 Файл бекапу: $BACKUP_PATH"
    echo "📏 Розмір архіву: $ARCHIVE_SIZE"
    echo "📊 Кількість файлів: $TOTAL_FILES"
    echo ""
    info "Бекап не містить логів та конфіденційної інформації"
    warn "Не забудьте налаштувати credentials.env після відновлення!"
else
    error "Помилка при створенні бекапу!"
    exit 1
fi
