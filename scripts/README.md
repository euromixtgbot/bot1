# Скрипти проекту Bot1

Ця папка містить допоміжні скрипти для обслуговування та розробки проекту.

## Структура

### `lint_tools/`
Інструменти для автоматичного виправлення та аналізу якості коду:
- `fix_e402.py` - виправлення імпортів після sys.path
- `fix_f541.py` - видалення f-prefix з strings без плейсхолдерів
- `fix_long_lines.py` - додавання noqa до довгих рядків
- `analyze_dead_code.py` - аналіз невикористовуваних функцій

Детальніше: [lint_tools/README.md](lint_tools/README.md)

### `activate_and_run.sh`
Активує віртуальне оточення та запускає бота.

**Використання:**
```bash
./scripts/activate_and_run.sh
```

## Корисні команди

### Перевірка якості коду
```bash
# Повна перевірка
flake8 src/ Tests/ --count --statistics

# Автоматичне форматування
black src/ Tests/

# Перевірка типів
mypy src/
```

### Запуск тестів
```bash
# Всі тести
pytest Tests/

# Конкретний тест
pytest Tests/test_specific.py
```

### Аналіз проекту
```bash
# Пошук мертвого коду
python scripts/lint_tools/analyze_dead_code.py

# Статистика коду
cloc src/ --exclude-dir=__pycache__
```
