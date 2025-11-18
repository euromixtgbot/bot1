#!/bin/bash
#
# Zabbix Auto-Configuration Script
# Автоматичне налаштування моніторингу бота через консоль
#

echo "============================================================"
echo "🚀 Автоматичне налаштування Zabbix для моніторингу бота"
echo "============================================================"
echo ""

# Перевірка, чи запущено Zabbix
if ! systemctl is-active --quiet zabbix-server; then
    echo "❌ Zabbix Server не запущено!"
    echo "Запустіть: systemctl start zabbix-server"
    exit 1
fi

echo "✅ Zabbix Server запущено"
echo ""

# Python скрипт для налаштування
python3 << 'PYEOF'
import requests
import json
import sys

ZABBIX_URL = "http://127.0.0.1:8080/zabbix/api_jsonrpc.php"
USERNAME = "Admin"
PASSWORD = "zabbix"

def api_call(method, params, auth=None):
    """Виклик Zabbix API"""
    data = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": 1
    }
    if auth:
        data["auth"] = auth
        
    try:
        response = requests.post(ZABBIX_URL, json=data, timeout=10)
        result = response.json()
        
        if 'error' in result:
            return None, result['error']['data']
        return result.get('result'), None
    except Exception as e:
        return None, str(e)

# Крок 1: Авторизація
print("🔐 Крок 1: Авторизація...")
auth, error = api_call("user.login", {"username": USERNAME, "password": PASSWORD})
if error:
    print(f"❌ Помилка авторизації: {error}")
    print("💡 Можливо, ви вже змінили пароль. Відредагуйте скрипт.")
    sys.exit(1)
print("✅ Авторизовано")

# Крок 2: Перевірка хоста
print("\n🖥️  Крок 2: Перевірка хоста bot02...")
host_data, error = api_call("host.get", {
    "filter": {"host": "bot02"},
    "selectInterfaces": "extend"
}, auth)

if host_data and len(host_data) > 0:
    print(f"✅ Хост вже існує (ID: {host_data[0]['hostid']})")
    hostid = host_data[0]['hostid']
    interfaceid = host_data[0]['interfaces'][0]['interfaceid']
else:
    # Створюємо хост
    print("📝 Створюємо хост bot02...")
    host_result, error = api_call("host.create", {
        "host": "bot02",
        "name": "Bot02 - Telegram Bot Monitoring",
        "groups": [{"groupid": "2"}],
        "templates": [{"templateid": "10343"}],
        "interfaces": [{
            "type": 1,
            "main": 1,
            "useip": 1,
            "ip": "127.0.0.1",
            "dns": "",
            "port": "10050"
        }]
    }, auth)
    
    if error:
        print(f"❌ Помилка створення хоста: {error}")
        sys.exit(1)
        
    hostid = host_result['hostids'][0]
    
    # Отримуємо interface ID
    host_data, _ = api_call("host.get", {
        "hostids": hostid,
        "selectInterfaces": "extend"
    }, auth)
    interfaceid = host_data[0]['interfaces'][0]['interfaceid']
    print(f"✅ Хост створено (ID: {hostid})")

# Крок 3: Створення items
print("\n📊 Крок 3: Створення items для моніторингу...")

items_config = [
    ("Bot Service Status", "bot.status", 1, ""),
    ("Bot Active Users", "bot.users.count", 3, ""),
    ("Bot Memory (KB)", "bot.memory", 3, "KB"),
    ("Bot CPU Usage", "bot.cpu", 0, "%"),
    ("Bot Monitor Status", "bot.monitor.status", 1, ""),
    ("Bot Uptime", "bot.uptime", 1, ""),
    ("Bot Log Errors", "bot.log.errors", 3, ""),
    ("Bot Log Size", "bot.log.size", 3, "B"),
    ("Nginx Status", "nginx.status", 1, ""),
    ("Bot Disk Usage", "disk.bot.usage", 3, "B"),
]

created_items = 0
for name, key, vtype, units in items_config:
    # Перевіряємо, чи існує
    existing, _ = api_call("item.get", {
        "hostids": hostid,
        "filter": {"key_": key}
    }, auth)
    
    if existing and len(existing) > 0:
        continue
        
    result, error = api_call("item.create", {
        "hostid": hostid,
        "interfaceid": interfaceid,
        "name": name,
        "key_": key,
        "type": 0,
        "value_type": vtype,
        "delay": "30s",
        "units": units
    }, auth)
    
    if result:
        print(f"  ✅ {name}")
        created_items += 1

if created_items == 0:
    print("  ℹ️  Всі items вже створені")
else:
    print(f"  ✅ Створено {created_items} нових items")

# Крок 4: Створення triggers
print("\n🚨 Крок 4: Створення triggers для сповіщень...")

triggers_config = [
    ("Bot service is down", f"last(/bot02/bot.status)<>\"active\"", 4),
    ("Bot monitor is down", f"last(/bot02/bot.monitor.status)<>\"active\"", 4),
    ("Nginx is down", f"last(/bot02/nginx.status)<>\"active\"", 4),
    ("High memory usage", f"last(/bot02/bot.memory)>100000", 3),
    ("Too many errors", f"last(/bot02/bot.log.errors)>10", 3),
]

created_triggers = 0
for name, expr, priority in triggers_config:
    # Перевіряємо, чи існує
    existing, _ = api_call("trigger.get", {
        "hostids": hostid,
        "filter": {"description": f"{name} on bot02"}
    }, auth)
    
    if existing and len(existing) > 0:
        continue
        
    result, error = api_call("trigger.create", {
        "description": f"{name} on bot02",
        "expression": expr,
        "priority": priority
    }, auth)
    
    if result:
        print(f"  ✅ {name}")
        created_triggers += 1

if created_triggers == 0:
    print("  ℹ️  Всі triggers вже створені")
else:
    print(f"  ✅ Створено {created_triggers} нових triggers")

# Крок 5: Створення dashboard
print("\n📈 Крок 5: Створення Dashboard...")

# Перевіряємо, чи існує
existing_dash, _ = api_call("dashboard.get", {
    "filter": {"name": "Bot Monitoring Dashboard"}
}, auth)

if existing_dash and len(existing_dash) > 0:
    print("  ℹ️  Dashboard вже існує")
else:
    # Отримуємо items для віджетів
    items_data, _ = api_call("item.get", {
        "hostids": hostid,
        "output": ["itemid", "name", "key_"]
    }, auth)
    
    items = {item['key_']: item['itemid'] for item in items_data}
    
    dashboard_result, error = api_call("dashboard.create", {
        "name": "Bot Monitoring Dashboard",
        "display_period": 30,
        "auto_start": 1,
        "pages": [{
            "name": "Main",
            "widgets": [
                {
                    "type": "item",
                    "name": "Bot Status",
                    "x": 0,
                    "y": 0,
                    "width": 4,
                    "height": 3,
                    "fields": [{"type": 0, "name": "itemid", "value": items.get('bot.status', '')}]
                },
                {
                    "type": "item",
                    "name": "Monitor Status",
                    "x": 4,
                    "y": 0,
                    "width": 4,
                    "height": 3,
                    "fields": [{"type": 0, "name": "itemid", "value": items.get('bot.monitor.status', '')}]
                },
                {
                    "type": "item",
                    "name": "Nginx Status",
                    "x": 8,
                    "y": 0,
                    "width": 4,
                    "height": 3,
                    "fields": [{"type": 0, "name": "itemid", "value": items.get('nginx.status', '')}]
                },
                {
                    "type": "item",
                    "name": "Active Users",
                    "x": 0,
                    "y": 3,
                    "width": 6,
                    "height": 3,
                    "fields": [{"type": 0, "name": "itemid", "value": items.get('bot.users.count', '')}]
                },
                {
                    "type": "item",
                    "name": "Memory Usage",
                    "x": 6,
                    "y": 3,
                    "width": 6,
                    "height": 3,
                    "fields": [{"type": 0, "name": "itemid", "value": items.get('bot.memory', '')}]
                }
            ]
        }]
    }, auth)
    
    if dashboard_result:
        print("  ✅ Dashboard створено")
    else:
        print(f"  ⚠️  Не вдалося створити dashboard: {error}")

print("\n" + "=" * 60)
print("✅ Налаштування завершено успішно!")
print("=" * 60)
print("")
print("📊 Що було налаштовано:")
print(f"  • Хост: bot02 (ID: {hostid})")
print(f"  • Items: {len(items_config)}")
print(f"  • Triggers: {len(triggers_config)}")
print(f"  • Dashboard: Bot Monitoring Dashboard")
print("")
print("🌐 Веб-інтерфейс:")
print("   http://157.180.46.236:8080/zabbix")
print("")
print("📊 Перегляд даних:")
print("   Monitoring → Latest data → bot02")
print("   Monitoring → Dashboards → Bot Monitoring Dashboard")
print("")
print("🔐 ВАЖЛИВО:")
print("   Змініть пароль адміністратора!")
print("   User icon → Profile → Password")
print("")
PYEOF

echo ""
echo "✅ Скрипт завершено"
echo ""
