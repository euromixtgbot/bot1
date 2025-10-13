# main.py

import logging
import sys
import os
import time
import asyncio
import signal
import fcntl
import subprocess
import ssl

# Add project root directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import httpx
    from telegram.ext import ApplicationBuilder
except ImportError as e:
    print(f"Import error: {e}")
    print("Please install required packages: pip install -r requirements.txt")
    sys.exit(1)

from config.config import (
    TELEGRAM_TOKEN,
    SSL_CERT_PATH,
    SSL_KEY_PATH,
    WEBHOOK_URL,
    WEBHOOK_HOST,
    WEBHOOK_PORT,
)

# Создаем директории, если они не существуют
os.makedirs("logs", exist_ok=True)

# Налаштування логування з ротацією файлів
from logging.handlers import RotatingFileHandler

# Отримуємо root logger
root_logger = logging.getLogger()

# Очищаємо всі існуючі handlers щоб запобігти дублюванню
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

# Налаштовуємо ротуючий файловий хендлер (10MB максимум, 10 файлів)
rotating_handler = RotatingFileHandler(
    "logs/bot.log",  # Фіксована назва для правильної ротації
    maxBytes=10 * 1024 * 1024,  # 10MB
    backupCount=10,  # Зберігати до 10 файлів (bot.log.1 ... bot.log.10)
    encoding="utf-8",
)

# Створюємо formatter
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
rotating_handler.setFormatter(formatter)

# Додаємо handlers до root logger
root_logger.setLevel(logging.INFO)
root_logger.addHandler(rotating_handler)

# Додаємо console handler ТІЛЬКИ якщо stdout НЕ перенаправлено в файл
# Це запобігає дублюванню логів коли бот запускається через nohup > file.log
if sys.stdout.isatty():
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

# Зменшуємо рівень логування для шумних бібліотек
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)
logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
logging.getLogger("aiohttp.server").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Глобальная переменная для хранения экземпляра приложения
_application = None

# Файл блокировки
LOCK_FILE = "logs/bot.lock"


# Функция для доступа к экземпляру приложения из других модулей
async def get_application():
    """
    Возвращает экземпляр приложения для использования в других модулях.

    Returns:
        Application: экземпляр приложения Telegram или None, если не инициализирован
    """
    return _application


def kill_existing_bot_processes():
    """Завершает все запущенные процессы бота, кроме текущего"""
    current_pid = os.getpid()
    try:
        # Находим все процессы python с main.py в командной строке
        result = subprocess.run(
            ["ps", "-eo", "pid,command"], capture_output=True, text=True, check=True
        )

        for line in result.stdout.splitlines():
            if "main.py" in line and "python" in line:
                try:
                    pid = int(line.split()[0])
                    if pid != current_pid:
                        logger.info(
                            f"Останавливаю существующий процесс бота: PID {pid}"
                        )
                        os.kill(pid, signal.SIGTERM)
                        time.sleep(0.5)  # Даем процессу время на завершение
                        # Проверяем, завершился ли процесс, если нет - SIGKILL
                        try:
                            os.kill(pid, 0)
                            logger.warning(
                                f"Процесс PID {pid} не завершился, использую SIGKILL"
                            )
                            os.kill(pid, signal.SIGKILL)
                        except OSError:
                            pass  # Процесс уже завершен
                except (ValueError, IndexError):
                    continue
    except Exception as e:
        logger.error(f"Ошибка при попытке остановить существующие процессы бота: {e}")


def acquire_lock():
    """Попытка получить блокировку, чтобы гарантировать запуск только одного экземпляра бота"""
    try:
        # Удаляем устаревший файл блокировки, если существует
        if os.path.exists(LOCK_FILE):
            try:
                os.unlink(LOCK_FILE)
                logger.info(f"Удален устаревший файл блокировки {LOCK_FILE}")
            except Exception as e:
                logger.warning(f"Не удалось удалить устаревший файл блокировки: {e}")

        lock_file = open(LOCK_FILE, "w")
        fcntl.lockf(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Записываем PID в файл блокировки
        lock_file.write(str(os.getpid()))
        lock_file.flush()
        logger.info("Получена блокировка для единственного экземпляра бота")
        return lock_file
    except IOError:
        logger.error("Не удалось получить блокировку. Возможно, бот уже запущен.")
        return None


async def reset_webhook():
    """Сброс webhook и состояния API Telegram перед запуском бота"""
    try:
        from config.config import TELEGRAM_TOKEN

        # Полный сброс состояния API Telegram
        logger.info("Начинаем сброс состояния API Telegram...")

        # 1. Удаляем webhook и все ожидающие обновления
        url_webhook = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook?drop_pending_updates=true"
        async with httpx.AsyncClient() as client:
            response = await client.post(url_webhook)
            response.raise_for_status()
            logger.info("Webhook и ожидающие обновления успешно сброшены")
            # Ждем небольшую паузу для гарантии обновления состояния API
            await asyncio.sleep(2)

        # 2. Делаем чистый запрос getUpdates с очисткой истории
        url_updates = (
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset=-1"
        )
        async with httpx.AsyncClient() as client:
            response = await client.post(url_updates)
            response.raise_for_status()
            logger.info(
                "История обновлений успешно сброшена через getUpdates?offset=-1"
            )
            # Дополнительная пауза для обновления состояния
            await asyncio.sleep(2)

    except Exception as e:
        logger.error(f"Ошибка сброса состояния API Telegram: {e}")


async def init_bot():
    """Ініціалізація бота з обробкою помилок"""
    try:
        # Створюємо та налаштовуємо Application
        application = (
            ApplicationBuilder()
            .token(TELEGRAM_TOKEN)
            .concurrent_updates(True)
            .connect_timeout(30.0)
            .write_timeout(30.0)
            .build()
        )

        # Реєструємо всі хендлери
        from src.handlers import register_handlers

        register_handlers(application)

        # Запускаємо бота
        await application.initialize()
        await application.start()

        # Устанавливаем глобальный экземпляр приложения для доступа из webhook handlers
        global _application
        _application = application

        logger.info("Бот успешно инициализирован")
        return application

    except Exception as e:
        logger.error(f"Помилка ініціалізації: {e}")
        return None


async def main():
    """Головна функція запуску бота"""
    # Инициализируем переменные
    lock_file = None
    application = None
    webhook_runner = None

    try:
        logger.info("====== Запуск бота ======")

        # Завершаем все существующие процессы бота
        kill_existing_bot_processes()

        # Проверка блокировки для предотвращения запуска нескольких экземпляров
        lock_file = acquire_lock()
        if not lock_file:
            logger.error("Завершение работы: другой экземпляр бота уже запущен")
            return

        logger.info("Бот запускається...")

        # Сброс состояния API Telegram перед запуском
        await reset_webhook()

        application = await init_bot()

        if not application:
            logger.error("Не вдалося запустити бота")
            return

        # Настройка и запуск webhook сервера для обработки вебхуков от Jira
        if WEBHOOK_URL and WEBHOOK_HOST and WEBHOOK_PORT:
            logger.info(f"Настраиваем webhook сервер на {WEBHOOK_HOST}:{WEBHOOK_PORT}")

            # Create SSL context if certificates are available
            ssl_context = None
            if (
                SSL_CERT_PATH
                and SSL_KEY_PATH
                and os.path.exists(SSL_CERT_PATH)
                and os.path.exists(SSL_KEY_PATH)
            ):
                ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                ssl_context.load_cert_chain(SSL_CERT_PATH, SSL_KEY_PATH)
                logger.info(
                    f"SSL контекст создан с сертификатами: {SSL_CERT_PATH}, {SSL_KEY_PATH}"
                )
            else:
                logger.warning(
                    "SSL сертификаты не найдены, будет использовано небезопасное соединение HTTP"
                )

            # Import webhook server setup and start it
            from src.jira_webhooks2 import setup_webhook_server

            webhook_runner = await setup_webhook_server(
                application,
                host=WEBHOOK_HOST,
                port=int(WEBHOOK_PORT),
                ssl_context=ssl_context,
            )
            logger.info(f"Webhook сервер запущен на {WEBHOOK_HOST}:{WEBHOOK_PORT}")
        else:
            logger.warning(
                "WEBHOOK_URL не настроен, вебхуки от Jira работать не будут!"
            )

        # ❌ ВИДАЛЕНО polling - використовуємо ТІЛЬКИ webhook для Telegram
        # Webhook обробляє ВСІ повідомлення: від користувачів AND від Jira
        # Polling + webhook конфліктують в Telegram Bot API

        # Встановлюємо webhook для Telegram Bot API
        if WEBHOOK_URL and WEBHOOK_HOST and WEBHOOK_PORT:
            try:
                # Встановлюємо webhook для отримання повідомлень від Telegram
                webhook_url = WEBHOOK_URL.replace(
                    "/rest/webhooks/webhook1", "/telegram"
                )
                await application.bot.set_webhook(
                    url=webhook_url,
                    drop_pending_updates=True,
                    allowed_updates=[
                        "message",
                        "callback_query",
                        "document",
                        "photo",
                        "video",
                        "audio",
                    ],
                )
                logger.info(f"Telegram webhook встановлено: {webhook_url}")
            except Exception as e:
                logger.error(f"Помилка встановлення Telegram webhook: {e}")

        # Ожидаем бесконечно (до Ctrl+C)
        logger.info("✅ Бот полностью запущен:")
        logger.info(
            "  - Telegram webhook: активен (получает сообщения от пользователей)"
        )
        if WEBHOOK_URL and WEBHOOK_HOST and WEBHOOK_PORT:
            logger.info(
                f"  - Jira webhook сервер: активен на {WEBHOOK_HOST}:{WEBHOOK_PORT}"
            )
        logger.info("Для остановки нажмите Ctrl+C")

        # Импортируем менеджер пользователей для синхронизации
        from user_management_service import user_manager

        try:
            sync_counter = 0
            while True:
                await asyncio.sleep(60)  # Перевірка кожну хвилину
                sync_counter += 1

                # Кожні 10 хвилин запускаємо синхронізацію
                if sync_counter % 10 == 0:
                    try:
                        result = user_manager.sync_pending_users()
                        if result["synced"] > 0 or result["failed"] > 0:
                            logger.info(
                                f"🔄 Синхронізація: {result['synced']} успішно, {result['failed']} помилок"
                            )
                    except Exception as e:
                        logger.error(f"Помилка планової синхронізації: {e}")
        except KeyboardInterrupt:
            logger.info("Получена команда завершения")
        finally:
            logger.info("Останавливаем сервисы...")
            await application.updater.stop()
            await application.stop()

    except KeyboardInterrupt:
        logger.info("Отримано команду на завершення")
    except Exception as e:
        logger.error(f"Критична помилка: {e}", exc_info=True)
    finally:
        # Очистка блокировки
        if lock_file:
            lock_file.close()
            try:
                os.unlink(LOCK_FILE)
            except:
                pass
        logger.info("Програма завершена")


if __name__ == "__main__":
    try:
        # Set the correct event loop policy to avoid potential conflicts
        # This helps with "Conflict: terminated by other getUpdates request" errors
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

        # Set longer timeouts for getUpdates operations
        os.environ["PYTHONASYNCIODEBUG"] = "1"  # Enable asyncio debugging

        # Run with proper exception handling
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except asyncio.CancelledError:
        logger.warning("Asyncio task was cancelled - this is expected during shutdown")
    except Exception as e:
        logger.critical(f"Fatal error in main thread: {e}", exc_info=True)
