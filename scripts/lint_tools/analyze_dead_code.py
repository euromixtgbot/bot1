#!/usr/bin/env python3
"""
Скрипт для глибокого аналізу невикористовуваних функцій у проекті Bot1
"""

import re
from pathlib import Path
from typing import Dict, List, Set, Tuple
from collections import defaultdict

# Директорії для аналізу
SOURCE_DIRS = ['src', 'config']
EXCLUDE_FILES = ['__init__.py', '__pycache__']

# Регулярні вирази
FUNCTION_DEF_PATTERN = re.compile(r'^(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', re.MULTILINE)
FUNCTION_CALL_PATTERN = re.compile(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(')
DECORATOR_PATTERN = re.compile(r'@([a-zA-Z_][a-zA-Z0-9_]*)')
IMPORT_PATTERN = re.compile(r'from\s+[\w.]+\s+import\s+(.+)|import\s+([\w.]+)')


class DeadCodeAnalyzer:
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.defined_functions: Dict[str, List[Tuple[str, int]]] = defaultdict(list)  # function_name -> [(file, line)]
        self.called_functions: Dict[str, Set[str]] = defaultdict(set)  # function_name -> {files where called}
        self.imported_functions: Dict[str, Set[str]] = defaultdict(set)  # function_name -> {files where imported}
        
    def find_python_files(self) -> List[Path]:
        """Знаходить всі Python файли для аналізу"""
        python_files = []
        for dir_name in SOURCE_DIRS:
            dir_path = self.base_path / dir_name
            if dir_path.exists():
                for py_file in dir_path.rglob('*.py'):
                    if not any(excl in str(py_file) for excl in EXCLUDE_FILES):
                        python_files.append(py_file)
        return sorted(python_files)
    
    def analyze_file(self, file_path: Path) -> None:
        """Аналізує один файл"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            rel_path = file_path.relative_to(self.base_path)
            
            # Знаходимо визначені функції
            for match in FUNCTION_DEF_PATTERN.finditer(content):
                func_name = match.group(1)
                # Знаходимо номер рядка
                line_num = content[:match.start()].count('\n') + 1
                self.defined_functions[func_name].append((str(rel_path), line_num))
            
            # Знаходимо виклики функцій
            for match in FUNCTION_CALL_PATTERN.finditer(content):
                func_name = match.group(1)
                self.called_functions[func_name].add(str(rel_path))
            
            # Знаходимо імпорти
            for match in IMPORT_PATTERN.finditer(content):
                imports = match.group(1) or match.group(2)
                if imports:
                    for imp in re.split(r'[,\s]+', imports):
                        clean_imp = imp.strip().split(' as ')[0]
                        if clean_imp:
                            self.imported_functions[clean_imp].add(str(rel_path))
            
            # Знаходимо декоратори (вони теж виклики функцій)
            for match in DECORATOR_PATTERN.finditer(content):
                decorator_name = match.group(1)
                self.called_functions[decorator_name].add(str(rel_path))
                
        except Exception as e:
            print(f"❌ Помилка аналізу {file_path}: {e}")
    
    def find_dead_functions(self) -> Dict[str, List[Tuple[str, int]]]:
        """Знаходить невикористовувані функції"""
        dead_functions = {}
        
        # Список спеціальних функцій які завжди використовуються
        ALWAYS_USED = {
            'main', '__init__', '__main__', '__name__',
            'get_application', 'init_bot', 'register_handlers',
            'handle_google_api_errors',  # декоратор
        }
        
        # Функції які використовуються як handlers у telegram
        HANDLER_PATTERNS = {
            '_handler', '_callback', 'start', 'cancel', 'help_handler',
            'dispatcher', 'middleware'
        }
        
        for func_name, definitions in self.defined_functions.items():
            # Пропускаємо спеціальні функції
            if func_name in ALWAYS_USED:
                continue
            
            # Пропускаємо handler функції (вони реєструються динамічно)
            if any(pattern in func_name for pattern in HANDLER_PATTERNS):
                continue
            
            # Пропускаємо приватні функції які використовуються в тому ж модулі
            if func_name.startswith('_'):
                # Перевіряємо чи є виклики в тому ж файлі
                for file_path, _ in definitions:
                    if file_path in self.called_functions.get(func_name, set()):
                        break
                else:
                    # Приватна функція не викликається навіть у своєму модулі
                    if func_name not in self.called_functions:
                        dead_functions[func_name] = definitions
                continue
            
            # Перевіряємо чи функція викликається або імпортується
            is_called = func_name in self.called_functions
            is_imported = func_name in self.imported_functions
            
            if not is_called and not is_imported:
                dead_functions[func_name] = definitions
        
        return dead_functions
    
    def analyze_all(self) -> Dict[str, List[Tuple[str, int]]]:
        """Виконує повний аналіз"""
        print("🔍 Початок аналізу невикористовуваних функцій...")
        print()
        
        # Знаходимо файли
        python_files = self.find_python_files()
        print(f"📁 Знайдено {len(python_files)} Python файлів:")
        for pf in python_files:
            print(f"   - {pf.relative_to(self.base_path)}")
        print()
        
        # Аналізуємо кожен файл
        print("🔎 Аналіз файлів...")
        for file_path in python_files:
            print(f"   ⚙️  {file_path.relative_to(self.base_path)}")
            self.analyze_file(file_path)
        
        print()
        print(f"✅ Знайдено визначень функцій: {len(self.defined_functions)}")
        print(f"✅ Знайдено унікальних викликів: {len(self.called_functions)}")
        print(f"✅ Знайдено імпортів: {len(self.imported_functions)}")
        print()
        
        # Знаходимо мертві функції
        dead_functions = self.find_dead_functions()
        
        return dead_functions
    
    def generate_report(self, dead_functions: Dict[str, List[Tuple[str, int]]]) -> str:
        """Генерує детальний звіт"""
        report = []
        report.append("# 🔍 Аналіз Невикористовуваних Функцій")
        report.append("")
        report.append(f"**Дата аналізу:** {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"**Всього функцій:** {len(self.defined_functions)}")
        report.append(f"**Невикористовуваних функцій:** {len(dead_functions)}")
        report.append("")
        report.append("---")
        report.append("")
        
        if not dead_functions:
            report.append("## ✅ Відмінно! Мертвого коду не знайдено.")
            report.append("")
            report.append("Всі визначені функції використовуються в проекті.")
        else:
            report.append(f"## ⚠️ Знайдено {len(dead_functions)} невикористовуваних функцій")
            report.append("")
            
            # Групуємо за файлами
            by_file = defaultdict(list)
            for func_name, definitions in sorted(dead_functions.items()):
                for file_path, line_num in definitions:
                    by_file[file_path].append((func_name, line_num))
            
            for file_path in sorted(by_file.keys()):
                report.append(f"### 📄 `{file_path}`")
                report.append("")
                
                funcs = sorted(by_file[file_path], key=lambda x: x[1])
                for func_name, line_num in funcs:
                    report.append(f"- **`{func_name}()`** (рядок {line_num})")
                    
                    # Додаємо інформацію чи є виклики
                    calls = self.called_functions.get(func_name, set())
                    imports = self.imported_functions.get(func_name, set())
                    
                    if calls:
                        report.append(f"  - 🔵 Викликається у: {', '.join(sorted(calls))}")
                    if imports:
                        report.append(f"  - 🟢 Імпортується у: {', '.join(sorted(imports))}")
                    
                    if not calls and not imports:
                        report.append(f"  - ❌ **Не викликається і не імпортується**")
                
                report.append("")
        
        report.append("---")
        report.append("")
        report.append("## 📊 Статистика по файлах")
        report.append("")
        
        # Статистика по файлах
        file_stats = defaultdict(lambda: {'total': 0, 'dead': 0})
        for func_name, definitions in self.defined_functions.items():
            for file_path, _ in definitions:
                file_stats[file_path]['total'] += 1
        
        for func_name, definitions in dead_functions.items():
            for file_path, _ in definitions:
                file_stats[file_path]['dead'] += 1
        
        report.append("| Файл | Всього функцій | Мертвих | % використання |")
        report.append("|------|----------------|---------|----------------|")
        
        for file_path in sorted(file_stats.keys()):
            total = file_stats[file_path]['total']
            dead = file_stats[file_path]['dead']
            usage = ((total - dead) / total * 100) if total > 0 else 100
            status = "✅" if usage == 100 else "⚠️" if usage >= 80 else "🔴"
            report.append(f"| `{file_path}` | {total} | {dead} | {status} {usage:.1f}% |")
        
        report.append("")
        report.append("---")
        report.append("")
        
        # Рекомендації
        if dead_functions:
            report.append("## 💡 Рекомендації")
            report.append("")
            report.append("### Перед видаленням перевірте:")
            report.append("")
            report.append("1. **Функції-handlers** - можуть бути зареєстровані динамічно")
            report.append("2. **Callback функції** - можуть передаватись як параметри")
            report.append("3. **Utility функції** - можуть бути для майбутнього використання")
            report.append("4. **API функції** - можуть викликатись ззовні")
            report.append("")
            report.append("### Безпечно видаляти якщо:")
            report.append("")
            report.append("- ✅ Функція не є handler/callback")
            report.append("- ✅ Функція не використовується в інших модулях")
            report.append("- ✅ Функція не планується до використання")
            report.append("- ✅ Є історія в Git (можна відновити)")
        
        return '\n'.join(report)


def main():
    """Головна функція"""
    analyzer = DeadCodeAnalyzer('/home/Bot1')
    
    # Виконуємо аналіз
    dead_functions = analyzer.analyze_all()
    
    # Генеруємо звіт
    report = analyzer.generate_report(dead_functions)
    
    # Зберігаємо звіт
    report_path = Path('/home/Bot1/reports/2025-10-08_DEAD_CODE_ANALYSIS.md')
    report_path.parent.mkdir(exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print("=" * 80)
    print()
    print(report)
    print()
    print("=" * 80)
    print()
    print(f"📝 Звіт збережено: {report_path}")
    
    # Короткий висновок
    if dead_functions:
        print(f"⚠️  Знайдено {len(dead_functions)} невикористовуваних функцій")
        print("🔍 Детальна інформація у звіті вище")
    else:
        print("✅ Мертвого коду не знайдено!")


if __name__ == '__main__':
    main()
