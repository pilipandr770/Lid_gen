import argparse
import asyncio
import os
import sys
from datetime import datetime
from typing import Optional
import pytz
from aiohttp import web

from config import settings

# HTTP сервер для health-check (Render Web Service)
async def health_handler(request):
    return web.Response(text="OK", status=200)

async def start_health_server():
    """Запускає HTTP сервер для health-check на порту з PORT env (або 10000)"""
    port = int(os.environ.get("PORT", 10000))
    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"[HTTP] Health-check server running on port {port}")
from telegram_client import make_client, resolve_linked_chat, get_admin_ids, iter_recent_discussion_messages, has_profile_photo, add_contact, get_contacts_list, is_contact_exists, get_subscribed_channels
from openai_classifier import (
    classify_comment, 
    create_batch_request, 
    save_batch_requests, 
    submit_batch,
    check_batch_status,
    download_batch_results,
    has_pending_batch
)
from storage import is_message_checked, mark_message_checked, cleanup_old_checked_messages, init_db

from telethon.errors import SessionPasswordNeededError
from telethon.tl.types import User

# Часова зона Києва
KYIV_TZ = pytz.timezone('Europe/Kyiv')

def _safe_name(user) -> str:
    parts = []
    if getattr(user, "first_name", None):
        parts.append(user.first_name)
    if getattr(user, "last_name", None):
        parts.append(user.last_name)
    return " ".join(parts).strip() or (user.username or f"id{user.id}")

async def login_flow(client):
    await client.connect()
    if not await client.is_user_authorized():
        phone = settings.telegram_phone
        if not phone:
            print("TELEGRAM_PHONE не задано у .env")
            sys.exit(1)
        await client.send_code_request(phone)
        code = input("Введи код з Telegram/SMS: ")
        try:
            await client.sign_in(phone=phone, code=code)
        except SessionPasswordNeededError:
            pw = input("Увімкнено 2FA. Введи пароль: ")
            await client.sign_in(password=pw)

async def scan_once(client, days_override: int = None, batch_size: int = None, use_batch_api: bool = False):
    """
    Сканує канали на наявність потенційних клієнтів.
    
    Args:
        client: Telegram клієнт
        days_override: Скільки днів назад перевіряти (замінює settings.days_lookback)
        batch_size: Скільки каналів обробити за раз (None = всі)
        use_batch_api: Використовувати Batch API (50% дешевше, але результати через 24 год)
    """
    from storage import is_message_checked, mark_message_checked
    
    days_to_check = days_override if days_override else settings.days_lookback

    # Отримуємо список контактів для перевірки наявності
    contacts_cache = await get_contacts_list(client)

    total_messages_processed = 0
    total_leads_found = 0
    skipped_already_checked = 0
    
    # Для batch режиму збираємо запити
    batch_requests = []
    pending_messages = []  # (msg, user, ch_ent, linked_id)

    channels_to_scan = []
    if settings.target_channels:
        channels_to_scan = settings.target_channels
    else:
        channels_to_scan = await get_subscribed_channels(client)
    
    # Обмежуємо кількість каналів якщо вказано batch_size
    if batch_size and len(channels_to_scan) > batch_size:
        channels_to_scan = channels_to_scan[:batch_size]

    mode = "BATCH" if use_batch_api else "REALTIME"
    print(f"[SCAN-{mode}] Перевіряю {len(channels_to_scan)} каналів за {days_to_check} днів...")

    for ch in channels_to_scan:
        try:
            ch_ent, linked_id = await resolve_linked_chat(client, ch)
            if not linked_id:
                continue

            admin_ids = await get_admin_ids(client, linked_id)
            
            # Прохід за коментарями
            message_count = 0
            leads_found = 0
            
            async for msg in iter_recent_discussion_messages(client, linked_id, days_to_check):
                message_count += 1
                
                # ОПТИМІЗАЦІЯ: Пропускаємо вже перевірені повідомлення
                if is_message_checked(msg.id):
                    skipped_already_checked += 1
                    continue
                
                if not msg.message or not msg.sender_id:
                    mark_message_checked(msg.id, linked_id)
                    continue
                
                user = await msg.get_sender()
                if not user or not isinstance(user, User):
                    mark_message_checked(msg.id, linked_id)
                    continue

                author_display = _safe_name(user)
                is_admin_or_verified = (user.id in admin_ids) or bool(getattr(user, "verified", False)) \
                    or bool(getattr(user, "bot", False))

                if use_batch_api:
                    # Збираємо запити для batch
                    custom_id = f"{msg.id}_{user.id}"
                    batch_req = create_batch_request(
                        custom_id=custom_id,
                        text=msg.message,
                        author_display=author_display,
                        is_verified_or_admin=is_admin_or_verified,
                        interest_keywords=settings.interest_keywords
                    )
                    batch_requests.append(batch_req)
                    pending_messages.append((msg, user, ch_ent, linked_id))
                else:
                    # Стандартна класифікація в реальному часі
                    cls = classify_comment(
                        text=msg.message,
                        author_display=author_display,
                        is_verified_or_admin=is_admin_or_verified,
                        interest_keywords=settings.interest_keywords
                    )

                    # Позначаємо як перевірене
                    mark_message_checked(msg.id, linked_id)

                    # Невелика затримка між запитами до OpenAI
                    await asyncio.sleep(0.5)

                    # Пропускаємо явних промо або низьку впевненість
                    if cls["role"] != "potential_client":
                        continue
                    if cls["confidence"] < settings.lead_confidence_threshold:
                        continue

                    # ДОДАТКОВА ПЕРЕВІРКА: наявність аватарки
                    has_photo = await has_profile_photo(client, user.id)
                    if not has_photo:
                        continue

                    # ПЕРЕВІРКА: чи контакт вже існує
                    if await is_contact_exists(client, user.id, contacts_cache):
                        continue

                    # Якщо всі умови виконані - додаємо контакт
                    first_name = getattr(user, "first_name", "")
                    last_name = getattr(user, "last_name", "")
                    phone = getattr(user, "phone", "")

                    contact_added = await add_contact(client, user.id, first_name, last_name, phone)
                    if contact_added:
                        leads_found += 1
                        print(f"[SCAN] ✅ Новий контакт: {author_display}")
                        contacts_cache.add(user.id)
                        await asyncio.sleep(1)

            total_messages_processed += message_count
            total_leads_found += leads_found
            
        except Exception as e:
            print(f"[SCAN ERROR] Канал {ch}: {e}")

    # Якщо batch режим - відправляємо запити
    if use_batch_api and batch_requests:
        print(f"[BATCH] 📦 Збережено {len(batch_requests)} запитів для batch обробки")
        save_batch_requests(batch_requests)
        submit_batch()
        # Зберігаємо pending_messages для подальшої обробки
        import json
        import os
        data_dir = os.getenv("DATA_DIR", ".")
        pending_file = os.path.join(data_dir, "pending_messages.json")
        pending_data = []
        for msg, user, ch_ent, linked_id in pending_messages:
            pending_data.append({
                "msg_id": msg.id,
                "user_id": user.id,
                "first_name": getattr(user, "first_name", ""),
                "last_name": getattr(user, "last_name", ""),
                "phone": getattr(user, "phone", ""),
                "linked_id": linked_id
            })
        with open(pending_file, "w", encoding="utf-8") as f:
            json.dump(pending_data, f)
        print(f"[BATCH] Результати будуть готові протягом 24 годин (50% дешевше!)")
    else:
        print(f"[SCAN] Готово! Оброблено: {total_messages_processed}, пропущено (кеш): {skipped_already_checked}, нових лідів: {total_leads_found}")

async def process_batch_results(client):
    """Обробляє результати batch запиту та додає контакти."""
    import json
    import os
    
    # Перевіряємо чи є результати
    status = check_batch_status()
    if status.get("status") != "completed":
        return
    
    print("[BATCH] 📥 Завантажую результати batch...")
    results = download_batch_results()
    
    if not results:
        return
    
    # Завантажуємо pending messages
    data_dir = os.getenv("DATA_DIR", ".")
    pending_file = os.path.join(data_dir, "pending_messages.json")
    
    if not os.path.exists(pending_file):
        print("[BATCH] Немає pending_messages.json")
        return
    
    with open(pending_file, "r", encoding="utf-8") as f:
        pending_data = json.load(f)
    
    contacts_cache = await get_contacts_list(client)
    leads_found = 0
    
    for item in pending_data:
        custom_id = f"{item['msg_id']}_{item['user_id']}"
        
        if custom_id not in results:
            continue
        
        cls = results[custom_id]
        
        # Позначаємо як перевірене
        mark_message_checked(item['msg_id'], item['linked_id'])
        
        # Фільтруємо
        if cls.get("role") != "potential_client":
            continue
        if cls.get("confidence", 0) < settings.lead_confidence_threshold:
            continue
        
        # Перевіряємо аватарку
        has_photo = await has_profile_photo(client, item['user_id'])
        if not has_photo:
            continue
        
        # Перевіряємо чи контакт існує
        if item['user_id'] in contacts_cache:
            continue
        
        # Додаємо контакт
        contact_added = await add_contact(
            client, 
            item['user_id'], 
            item['first_name'], 
            item['last_name'], 
            item['phone']
        )
        
        if contact_added:
            leads_found += 1
            name = f"{item['first_name']} {item['last_name']}".strip()
            print(f"[BATCH] ✅ Новий контакт: {name}")
            contacts_cache.add(item['user_id'])
            await asyncio.sleep(1)
    
    # Видаляємо pending file
    os.remove(pending_file)
    print(f"[BATCH] ✅ Оброблено batch результати, нових лідів: {leads_found}")


async def stream_loop():
    """
    Головний цикл бота з розумним розкладом:
    
    🌙 00:00 - 08:59 (ніч): Повне сканування всіх каналів за 7 днів
    ☀️ 09:00 - 20:59 (день): Розсилка + контент, швидке сканування (1 день)
    🌆 21:00 - 23:59 (вечір): Швидке сканування (1 день)
    """
    from sender import process_invites
    from content_bot import process_content
    
    # Запускаємо HTTP сервер для health-check (Render Web Service)
    await start_health_server()
    
    # Ініціалізуємо базу даних
    init_db()
    
    client = make_client()
    await login_flow(client)
    
    async with client:
        print("[APP] 🚀 Бот запущено!")
        print("[APP] Розклад:")
        print("[APP]   🌙 00:00-08:59: Batch сканування (7 днів, 50% дешевше)")
        print("[APP]   ☀️ 09:00-20:59: Розсилка + контент + швидке сканування (1 день)")
        print("[APP]   🌆 21:00-23:59: Швидке сканування (1 день)")
        
        last_full_scan_date = None
        last_batch_check_hour = None
        
        while True:
            try:
                kyiv_now = datetime.now(KYIV_TZ)
                current_hour = kyiv_now.hour
                current_date = kyiv_now.date()
                
                # Перевіряємо batch результати кожну годину
                if last_batch_check_hour != current_hour:
                    if has_pending_batch():
                        status = check_batch_status()
                        print(f"[BATCH] Статус: {status.get('status')}")
                        if status.get("status") == "completed":
                            await process_batch_results(client)
                    last_batch_check_hour = current_hour
                
                # Очищення старих записів раз на добу о 3:00
                if current_hour == 3 and last_full_scan_date != current_date:
                    deleted = cleanup_old_checked_messages(days=14)
                    if deleted > 0:
                        print(f"[APP] 🧹 Очищено {deleted} старих записів з кешу")
                
                # 🌙 НІЧ (00:00 - 08:59): Batch сканування (50% дешевше)
                if current_hour < 9:
                    # Повне сканування раз на ніч через Batch API
                    if last_full_scan_date != current_date and not has_pending_batch():
                        print(f"[APP] 🌙 Нічний режим: batch сканування (50% економія)...")
                        await scan_once(client, days_override=7, use_batch_api=True)
                        last_full_scan_date = current_date
                        await asyncio.sleep(1800)  # 30 хв пауза
                    else:
                        if has_pending_batch():
                            print(f"[APP] 🌙 Нічний режим: очікування batch результатів...")
                        else:
                            print(f"[APP] 🌙 Нічний режим: очікування (batch вже відправлено)")
                        await asyncio.sleep(600)  # 10 хв
                
                # ☀️ ДЕНЬ (09:00 - 20:59): Активна робота
                elif current_hour < 21:
                    print(f"[APP] ☀️ Денний режим ({kyiv_now.strftime('%H:%M')} Київ)")
                    
                    # Швидке сканування (тільки за 1 день, realtime API)
                    await scan_once(client, days_override=1, use_batch_api=False)
                    
                    # Розсилка запрошень
                    await process_invites(client)
                    
                    # Публікація контенту
                    await process_content(client)
                    
                    await asyncio.sleep(300)  # 5 хв пауза
                
                # 🌆 ВЕЧІР (21:00 - 23:59): Тільки сканування
                else:
                    print(f"[APP] 🌆 Вечірній режим ({kyiv_now.strftime('%H:%M')} Київ)")
                    await scan_once(client, days_override=1, use_batch_api=False)
                    await asyncio.sleep(600)  # 10 хв пауза
                
            except Exception as e:
                print(f"[APP ERROR] {e}")
                await asyncio.sleep(60)  # 1 хв пауза при помилці

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Разове сканування")
    parser.add_argument("--stream", action="store_true", help="Безкінечний цикл (кожні 5 хвилин)")
    args = parser.parse_args()

    if not settings.openai_api_key:
        print("OPENAI_API_KEY не вказано у .env.")
        sys.exit(1)

    if args.stream:
        asyncio.run(stream_loop())
    else:
        async def run_once():
            init_db()
            client = make_client()
            await login_flow(client)
            async with client:
                await scan_once(client)
        asyncio.run(run_once())

if __name__ == "__main__":
    main()