import asyncio
import os
import time
import random
from datetime import datetime, timedelta
import pytz
from telethon import TelegramClient
from messages_config import INVITE_MESSAGES
from telegram_client import get_contacts_list

# Часова зона Києва
KYIV_TZ = pytz.timezone('Europe/Kyiv')

# Використовуємо DATA_DIR для збереження стану
data_dir = os.getenv("DATA_DIR", ".")
SENT_USERS_FILE = os.path.join(data_dir, "sent_users.txt")
LAST_RUN_FILE = os.path.join(data_dir, "last_sender_run.txt")

def load_sent_users():
    if not os.path.exists(SENT_USERS_FILE):
        return set()
    with open(SENT_USERS_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def save_sent_user(user_id):
    with open(SENT_USERS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{user_id}\n")

def get_last_run_time():
    if not os.path.exists(LAST_RUN_FILE):
        return 0
    try:
        with open(LAST_RUN_FILE, "r") as f:
            return float(f.read().strip())
    except:
        return 0

def update_last_run_time():
    with open(LAST_RUN_FILE, "w") as f:
        f.write(str(time.time()))

async def process_invites(client: TelegramClient):
    """
    Відправляє одне запрошення одному контакту, якщо пройшло 15 хвилин з останньої розсилки.
    Працює тільки з 9:00 до 21:00 за Київським часом.
    """
    # Перевірка робочих годин (9:00 - 21:00 за Києвом)
    kyiv_now = datetime.now(KYIV_TZ)
    if kyiv_now.hour < 9 or kyiv_now.hour >= 21:
        print(f"[SENDER] Зараз {kyiv_now.strftime('%H:%M')} (Київ) - неробочі години, пропускаємо")
        return
    
    last_run = get_last_run_time()
    now = time.time()
    
    # Перевірка чи пройшло 15 хвилин (900 секунд)
    if now - last_run < 900:
        return

    try:
        # Отримуємо контакти
        contacts = await get_contacts_list(client)
        sent_users = load_sent_users()
        
        # Знаходимо тих, кому ще не писали
        candidates = [uid for uid in contacts if str(uid) not in sent_users]
        
        if not candidates:
            return

        # Беремо наступного кандидата (першого зі списку)
        target_user_id = candidates[0]
        
        # Вибираємо випадкове повідомлення з 3 варіантів
        message = random.choice(INVITE_MESSAGES)
        
        # Відправляємо
        await client.send_message(target_user_id, message)
        print(f"[SENDER] Відправлено запрошення користувачу {target_user_id}")
        
        # Зберігаємо статус
        save_sent_user(target_user_id)
        update_last_run_time()
        
    except Exception as e:
        print(f"[SENDER ERROR] {e}")
