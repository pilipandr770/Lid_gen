import argparse
import asyncio
import sys
from typing import Optional

from config import settings
from telegram_client import make_client, resolve_linked_chat, get_admin_ids, iter_recent_discussion_messages, has_profile_photo, add_contact, get_contacts_list, is_contact_exists, get_subscribed_channels
from openai_classifier import classify_comment

from telethon.errors import SessionPasswordNeededError
from telethon.tl.types import User

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

async def scan_once():
    client = make_client()
    await login_flow(client)

    async with client:
        # Отримуємо список контактів для перевірки наявності
        print("[INFO] Завантаження списку контактів...")
        contacts_cache = await get_contacts_list(client)
        print(f"[INFO] Знайдено {len(contacts_cache)} контактів у адресній книзі")

        total_messages_processed = 0
        total_leads_found = 0

        channels_to_scan = []
        if settings.target_channels:
            channels_to_scan = settings.target_channels
        else:
            print("[INFO] TARGET_CHANNELS не вказано, отримую список підписок...")
            channels_to_scan = await get_subscribed_channels(client)
            print(f"[INFO] Знайдено {len(channels_to_scan)} каналів.")

        for ch in channels_to_scan:
            try:
                # Для логування назви каналу
                ch_name = ch if isinstance(ch, str) else getattr(ch, 'title', getattr(ch, 'username', 'Unknown'))
                print(f"[INFO] Сканування каналу: {ch_name}")
                
                ch_ent, linked_id = await resolve_linked_chat(client, ch)
                if not linked_id:
                    print(f"[WARN] Канал {ch_name}: немає пов'язаного чату для коментарів.")
                    continue

                admin_ids = await get_admin_ids(client, linked_id)
                print(f"[INFO] Знайдено {len(admin_ids)} адмінів у чаті")
                
                # Прохід за коментарями
                message_count = 0
                leads_found = 0
                
                async for msg in iter_recent_discussion_messages(client, linked_id, settings.days_lookback):
                    message_count += 1
                    if not msg.message or not msg.sender_id:
                        continue
                    
                    user = await msg.get_sender()
                    if not user or not isinstance(user, User):
                        continue

                    author_display = _safe_name(user)
                    is_admin_or_verified = (user.id in admin_ids) or bool(getattr(user, "verified", False)) \
                        or bool(getattr(user, "bot", False))

                    # Класифікація
                    cls = classify_comment(
                        text=msg.message,
                        author_display=author_display,
                        is_verified_or_admin=is_admin_or_verified,
                        interest_keywords=settings.interest_keywords
                    )

                    # Невелика затримка між запитами до OpenAI
                    import asyncio
                    await asyncio.sleep(0.5)

                    # Пропускаємо явних промо або низьку впевненість
                    if cls["role"] != "potential_client":
                        continue
                    if cls["confidence"] < settings.lead_confidence_threshold:
                        continue

                    username = f"@{user.username}" if user.username else ""
                    # Побудова посилання на повідомлення
                    msg_link = ""
                    if hasattr(ch_ent, "username") and ch_ent.username:
                        # Для публічних чатів можна спробувати побудувати лінк
                        msg_link = f"https://t.me/{ch_ent.username}/{msg.id}"

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
                        # Оновлюємо кеш контактів
                        contacts_cache.add(user.id)
                        print(f"[SUCCESS] Додано контакт: {author_display}")
                        print(f"         Повідомлення: {msg.message[:100]}...")

                        # Додаємо невелику затримку між додаваннями контактів
                        import asyncio
                        await asyncio.sleep(1)
                    else:
                        print(f"[SKIP] {author_display}: не вдалося додати контакт")

                print(f"[OK] Канал {ch}: переглянуто {message_count} повідомлень, додано {leads_found} контактів")
                total_messages_processed += message_count
                total_leads_found += leads_found
                
            except Exception as e:
                print(f"[ERROR] {ch}: {e}")

        print(f"\n[STATS] Сканування завершено:")
        print(f"  - Переглянуто повідомлень: {total_messages_processed}")
        print(f"  - Додано контактів: {total_leads_found}")
        print(f"  - Загалом контактів: {len(contacts_cache)}")

async def stream_loop():
    # Простий "пульс" кожні N хвилин — можеш замінити на планувальник/Windows Task Scheduler
    import time
    while True:
        try:
            print(f"[STREAM] Початок циклу сканування...")
            await scan_once()
            print(f"[STREAM] Цикл завершено. Пауза 5 хвилин...")
        except Exception as e:
            print("[STREAM ERROR]", e)
        time.sleep(300)  # 5 хвилин пауза

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Разове сканування")
    parser.add_argument("--stream", action="store_true", help="Безкінечний цикл (кожні 5 хвилин)")
    args = parser.parse_args()

    if not settings.openai_api_key:
        print("OPENAI_API_KEY не вказано у .env.")
        sys.exit(1)

    print(f"[INFO] Налаштування завантажено:")
    if settings.target_channels:
        print(f"  - Канали (з .env): {settings.target_channels}")
    else:
        print(f"  - Канали: Всі підписки (TARGET_CHANNELS пустий)")
    print(f"  - Ключові слова: {settings.interest_keywords}")
    print(f"  - Ключові слова: {settings.interest_keywords}")
    print(f"  - Днів назад: {settings.days_lookback}")
    print(f"  - Поріг впевненості: {settings.lead_confidence_threshold}")

    if args.stream:
        asyncio.run(stream_loop())
    else:
        asyncio.run(scan_once())

if __name__ == "__main__":
    main()