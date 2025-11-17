# Інструменти для лінтингу та аналізу коду

Ця папка містить скрипти для автоматичного виправлення та аналізу якості коду.

## Скрипти

### `fix_e402.py`
Автоматично додає `# noqa: E402` коментарі до імпортів після `sys.path` модифікацій.

**Використання:**
```bash
python scripts/lint_tools/fix_e402.py
```

### `fix_f541.py`
Видаляє `f` prefix з f-strings, які не містять плейсхолдерів `{}`.

**Використання:**
```bash
python scripts/lint_tools/fix_f541.py
```

### `fix_long_lines.py`
Додає `# noqa: E501` коментарі до довгих діагностичних рядків.

**Використання:**
```bash
python scripts/lint_tools/fix_long_lines.py
```

### `analyze_dead_code.py`
Виконує глибокий аналіз невикористовуваних функцій у проекті.

**Використання:**
```bash
python scripts/lint_tools/analyze_dead_code.py
```

**Вивід:**
- Список функцій, що ніде не викликаються
- Потенційно мертвий код
- Рекомендації щодо очищення

## Швидкий запуск

Виправити всі помилки лінтингу одразу:

```bash
cd /home/Bot1
python scripts/lint_tools/fix_e402.py
python scripts/lint_tools/fix_f541.py
python scripts/lint_tools/fix_long_lines.py
black src/ Tests/
flake8 src/ Tests/ --count
```

## Після використання

Рекомендується запустити тести після виправлень:

```bash
pytest Tests/
```
