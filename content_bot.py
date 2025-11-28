"""
Головний модуль контент-бота.
Читає RSS → Генерує статті через AI → Публікує в Telegram канал.
"""
import asyncio
import os
import time
from datetime import datetime
import pytz

from dotenv import load_dotenv
load_dotenv()

from telegram_client import make_client
from rss_fetcher import fetch_rss_feeds, mark_article_as_processed
from content_generator import generate_article

# Часова зона Києва
KYIV_TZ = pytz.timezone('Europe/Kyiv')

# Налаштування
data_dir = os.getenv("DATA_DIR", ".")
if data_dir == "/data" and not os.path.exists("/data"):
    data_dir = "."  # Якщо /data не існує (локальний запуск), використовуємо поточну папку
LAST_CONTENT_RUN_FILE = os.path.join(data_dir, "last_content_run.txt")


def get_rss_feeds() -> list:
    """Отримує список RSS стрічок з .env"""
    feeds_str = os.getenv("RSS_FEEDS", "")
    return [f.strip() for f in feeds_str.split(",") if f.strip()]


def get_content_channel() -> str:
    """Отримує канал для публікації"""
    return os.getenv("CONTENT_CHANNEL", "")


def get_interval_hours() -> int:
    """Отримує інтервал публікації в годинах"""
    return int(os.getenv("CONTENT_INTERVAL_HOURS", "4"))


def get_last_run_time() -> float:
    if not os.path.exists(LAST_CONTENT_RUN_FILE):
        return 0
    try:
        with open(LAST_CONTENT_RUN_FILE, "r") as f:
            return float(f.read().strip())
    except:
        return 0


def update_last_run_time():
    with open(LAST_CONTENT_RUN_FILE, "w") as f:
        f.write(str(time.time()))


async def publish_content(client, channel: str, content: str) -> bool:
    """Публікує контент в канал."""
    try:
        await client.send_message(channel, content)
        print(f"[CONTENT] ✅ Опубліковано в {channel}")
        return True
    except Exception as e:
        print(f"[CONTENT ERROR] Помилка публікації: {e}")
        return False


async def process_content(client):
    """
    Основна функція обробки контенту.
    Перевіряє чи пройшов інтервал, отримує RSS, генерує та публікує.
    """
    # Перевірка інтервалу
    last_run = get_last_run_time()
    now = time.time()
    interval_seconds = get_interval_hours() * 3600
    
    if now - last_run < interval_seconds:
        remaining = int((interval_seconds - (now - last_run)) / 60)
        print(f"[CONTENT] До наступної публікації: {remaining} хв")
        return
    
    # Перевірка робочих годин (9:00 - 21:00 за Києвом)
    kyiv_now = datetime.now(KYIV_TZ)
    if kyiv_now.hour < 9 or kyiv_now.hour >= 21:
        print(f"[CONTENT] Зараз {kyiv_now.strftime('%H:%M')} (Київ) - неробочі години")
        return
    
    # Отримуємо налаштування
    feeds = get_rss_feeds()
    channel = get_content_channel()
    
    if not feeds:
        print("[CONTENT] RSS_FEEDS не налаштовано в .env")
        return
    
    if not channel:
        print("[CONTENT] CONTENT_CHANNEL не налаштовано в .env")
        return
    
    print(f"[CONTENT] Перевіряю {len(feeds)} RSS джерел...")
    
    # Отримуємо нові статті
    articles = fetch_rss_feeds(feeds)
    
    if not articles:
        print("[CONTENT] Немає нових статей")
        update_last_run_time()  # Все одно оновлюємо час щоб не спамити
        return
    
    print(f"[CONTENT] Знайдено {len(articles)} нових статей")
    
    # Пробуємо згенерувати контент (перебираємо поки не знайдемо підходящу)
    for article in articles:
        print(f"[CONTENT] Обробляю: {article['title'][:60]}...")
        
        content = generate_article(article)
        
        if content:
            # Публікуємо
            success = await publish_content(client, channel, content)
            
            if success:
                mark_article_as_processed(article["id"])
                update_last_run_time()
                return  # Публікуємо тільки 1 статтю за раз
        
        # Позначаємо як оброблену навіть якщо пропустили
        mark_article_as_processed(article["id"])
    
    print("[CONTENT] Жодна стаття не пройшла фільтр")
    update_last_run_time()


async def content_loop():
    """Безкінечний цикл контент-бота."""
    from app import login_flow
    
    client = make_client()
    await login_flow(client)
    
    async with client:
        print("[CONTENT BOT] Запущено!")
        print(f"[CONTENT BOT] Інтервал: кожні {get_interval_hours()} години")
        print(f"[CONTENT BOT] Канал: {get_content_channel()}")
        
        while True:
            try:
                await process_content(client)
            except Exception as e:
                print(f"[CONTENT ERROR] {e}")
            
            await asyncio.sleep(300)  # Перевірка кожні 5 хвилин


async def run_once():
    """Одноразовий запуск (для тестування)."""
    from app import login_flow
    
    client = make_client()
    await login_flow(client)
    
    async with client:
        # Примусово скидаємо таймер для тесту
        if os.path.exists(LAST_CONTENT_RUN_FILE):
            os.remove(LAST_CONTENT_RUN_FILE)
        
        await process_content(client)


if __name__ == "__main__":
    import sys
    
    if "--once" in sys.argv:
        print("[CONTENT BOT] Одноразовий запуск...")
        asyncio.run(run_once())
    else:
        print("[CONTENT BOT] Запуск в режимі циклу...")
        asyncio.run(content_loop())
