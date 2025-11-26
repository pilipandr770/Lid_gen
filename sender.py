import asyncio
import os
import time
import random
from datetime import datetime, timedelta
from telethon import TelegramClient
from messages_config import INVITE_MESSAGES
from telegram_client import get_contacts_list

SENT_USERS_FILE = "sent_users.txt"
LAST_RUN_FILE = "last_sender_run.txt"

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
    Відправляє одне запрошення одному контакту, якщо пройшло 30 хвилин з останньої розсилки.
    """
    last_run = get_last_run_time()
    now = time.time()
    
    # Перевірка чи пройшло 30 хвилин (1800 секунд)
    if now - last_run < 1800:
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
