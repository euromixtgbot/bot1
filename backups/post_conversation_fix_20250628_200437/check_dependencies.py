#!/usr/bin/env python3
"""
Скрипт для проверки всех зависимостей проекта
"""

import sys
import importlib
import traceback

# Список основных зависимостей
REQUIRED_PACKAGES = [
    'telegram',
    'httpx', 
    'aiohttp',
    'dotenv',
    'yaml',
    'gspread',
    'google.auth',
    'requests',
    'asyncio',
    'json',
    'logging'
]

def check_package(package_name):
    """Проверяет доступность пакета"""
    try:
        module = importlib.import_module(package_name)
        version = getattr(module, '__version__', 'unknown')
        print(f"✅ {package_name}: {version}")
        return True
    except ImportError as e:
        print(f"❌ {package_name}: {e}")
        return False
    except Exception as e:
        print(f"⚠️  {package_name}: {e}")
        return False

def main():
    print("🔍 Проверка зависимостей проекта...\n")
    
    failed_packages = []
    
    for package in REQUIRED_PACKAGES:
        if not check_package(package):
            failed_packages.append(package)
    
    print(f"\n📊 Результаты проверки:")
    print(f"✅ Доступно: {len(REQUIRED_PACKAGES) - len(failed_packages)}/{len(REQUIRED_PACKAGES)}")
    print(f"❌ Недоступно: {len(failed_packages)}")
    
    if failed_packages:
        print(f"\n🛠️  Установите недостающие пакеты:")
        print("pip install " + " ".join(failed_packages))
        return 1
    else:
        print("\n🎉 Все зависимости установлены!")
        return 0

if __name__ == "__main__":
    sys.exit(main())
