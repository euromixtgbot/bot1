#!/usr/bin/env python3
"""
Валідатор для JSON файлів станів користувачів.
Використовується для перевірки структури та цілісності даних.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime


class UserStateValidator:
    """Валідатор для перевірки JSON файлів станів користувачів."""
    
    def __init__(self, user_states_dir: str = "user_states"):
        """
        Ініціалізація валідатора.
        
        Args:
            user_states_dir: Папка зі станами користувачів
        """
        self.user_states_dir = Path(user_states_dir)
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def validate_user_state_structure(self, user_data: Dict[str, Any]) -> bool:
        """
        Валідація структури даних користувача.
        
        Args:
            user_data: Дані користувача для валідації
            
        Returns:
            True якщо структура валідна, False інакше
        """
        required_fields = ['telegram_id', 'last_updated', 'state']
        
        for field in required_fields:
            if field not in user_data:
                self.errors.append(f"Відсутнє обов'язкове поле: {field}")
                return False
        
        # Перевірка типів
        if not isinstance(user_data['telegram_id'], int):
            self.errors.append("telegram_id повинен бути integer")
            return False
        
        # Перевірка формату дати
        try:
            datetime.fromisoformat(user_data['last_updated'])
        except ValueError:
            self.errors.append(f"Невірний формат дати: {user_data['last_updated']}")
            return False
        
        # Валідація структури профілю
        if 'profile' in user_data['state']:
            profile = user_data['state']['profile']
            profile_required = ['full_name', 'division', 'department', 'mobile_number', 'telegram_id']
            
            for field in profile_required:
                if field not in profile:
                    self.warnings.append(f"Відсутнє поле профілю: {field}")
        
        return True
    
    def validate_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """
        Валідація одного JSON файлу.
        
        Args:
            file_path: Шлях до файлу
            
        Returns:
            Дані користувача якщо файл валідний, None інакше
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                user_data = json.load(f)
            
            if self.validate_user_state_structure(user_data):
                return user_data
            
        except json.JSONDecodeError as e:
            self.errors.append(f"Помилка JSON у файлі {file_path}: {e}")
        except FileNotFoundError:
            self.errors.append(f"Файл не знайдено: {file_path}")
        except Exception as e:
            self.errors.append(f"Невідома помилка у файлі {file_path}: {e}")
        
        return None
    
    def validate_all_files(self) -> Dict[str, Any]:
        """
        Валідація всіх JSON файлів у папці user_states.
        
        Returns:
            Словник з результатами валідації
        """
        if not self.user_states_dir.exists():
            return {
                'success': False,
                'error': f"Папка {self.user_states_dir} не існує"
            }
        
        json_files = list(self.user_states_dir.glob("*.json"))
        valid_files = []
        invalid_files = []
        
        for file_path in json_files:
            user_data = self.validate_file(file_path)
            if user_data:
                valid_files.append({
                    'file': str(file_path),
                    'telegram_id': user_data['telegram_id'],
                    'last_updated': user_data['last_updated']
                })
            else:
                invalid_files.append(str(file_path))
        
        return {
            'success': len(self.errors) == 0,
            'total_files': len(json_files),
            'valid_files': len(valid_files),
            'invalid_files': len(invalid_files),
            'files_details': valid_files,
            'errors': self.errors,
            'warnings': self.warnings
        }
    
    def get_user_statistics(self) -> Dict[str, Any]:
        """
        Отримання статистики користувачів.
        
        Returns:
            Словник зі статистикою
        """
        stats = {
            'total_users': 0,
            'active_users': 0,
            'divisions': set(),
            'departments': set(),
            'sync_enabled': 0,
            'last_activity': None
        }
        
        json_files = list(self.user_states_dir.glob("*.json"))
        
        for file_path in json_files:
            user_data = self.validate_file(file_path)
            if user_data:
                stats['total_users'] += 1
                
                state = user_data.get('state', {})
                
                # Статус користувача
                if state.get('status') == 'active':
                    stats['active_users'] += 1
                
                # Профіль користувача
                profile = state.get('profile', {})
                if profile.get('division'):
                    stats['divisions'].add(profile['division'])
                if profile.get('department'):
                    stats['departments'].add(profile['department'])
                
                # Синхронізація
                if state.get('sync_with_google'):
                    stats['sync_enabled'] += 1
                
                # Остання активність
                last_updated = user_data.get('last_updated')
                if last_updated:
                    if not stats['last_activity'] or last_updated > stats['last_activity']:
                        stats['last_activity'] = last_updated
        
        # Конвертуємо sets у lists для JSON serialization
        stats['divisions'] = list(stats['divisions'])
        stats['departments'] = list(stats['departments'])
        
        return stats


def main():
    """Основна функція для запуску валідації."""
    validator = UserStateValidator()
    
    print("🔍 Валідація JSON файлів станів користувачів...")
    results = validator.validate_all_files()
    
    if results['success']:
        print("✅ Всі файли валідні!")
        print(f"📊 Статистика: {results['valid_files']}/{results['total_files']} файлів")
        
        # Показуємо статистику користувачів
        stats = validator.get_user_statistics()
        print(f"\n📈 Статистика користувачів:")
        print(f"   Всього користувачів: {stats['total_users']}")
        print(f"   Активних користувачів: {stats['active_users']}")
        print(f"   Відділи: {', '.join(stats['divisions'])}")
        print(f"   Департаменти: {', '.join(stats['departments'])}")
        print(f"   З увімкненою синхронізацією: {stats['sync_enabled']}")
        if stats['last_activity']:
            print(f"   Остання активність: {stats['last_activity']}")
        
    else:
        print("❌ Знайдено помилки:")
        for error in results['errors']:
            print(f"   • {error}")
    
    if results['warnings']:
        print("\n⚠️ Попередження:")
        for warning in results['warnings']:
            print(f"   • {warning}")


if __name__ == "__main__":
    main()
