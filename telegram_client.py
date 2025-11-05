import datetime as dt
from typing import List, Optional, Tuple
from telethon import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.contacts import ImportContactsRequest, GetContactsRequest
from telethon.tl.types import Channel, ChannelParticipantsAdmins, InputPhoneContact
from config import settings

SESSION_NAME = "tg_session"

def make_client() -> TelegramClient:
    return TelegramClient(SESSION_NAME, settings.telegram_api_id, settings.telegram_api_hash)

async def resolve_linked_chat(client: TelegramClient, channel_username: str) -> Tuple[Optional[Channel], Optional[int]]:
    """
    Повертає (ChannelEntity, linked_chat_id) для каналу; якщо немає прив'язаного чату — (entity, None).
    """
    entity = await client.get_entity(channel_username)
    full = await client(GetFullChannelRequest(channel=entity))
    linked = getattr(full.full_chat, "linked_chat_id", None)
    return entity, linked

async def get_admin_ids(client: TelegramClient, chat_id: int) -> set[int]:
    admin_ids = set()
    try:
        async for p in client.iter_participants(chat_id, filter=ChannelParticipantsAdmins()):
            if p and p.id:
                admin_ids.add(p.id)
    except Exception as e:
        print(f"[WARN] Не вдалося отримати список адмінів для {chat_id}: {e}")
    return admin_ids

async def iter_recent_discussion_messages(client: TelegramClient, chat_id: int, days_back: int):
    """
    Ітерує повідомлення з пов'язаного чату за останні days_back днів.
    """
    cutoff = dt.datetime.utcnow() - dt.timedelta(days=days_back)
    async for msg in client.iter_messages(chat_id, offset_date=None, reverse=False):
        if msg.date is None:
            continue
        if msg.date.replace(tzinfo=None) < cutoff:
            break
        yield msg

async def has_profile_photo(client: TelegramClient, user_id: int) -> bool:
    """
    Перевіряє, чи має користувач фотографію на аватарці.
    """
    try:
        photos = await client.get_profile_photos(user_id, limit=1)
        return len(photos) > 0
    except Exception as e:
        # Тихо обробляємо помилки - користувач може бути недоступний
        return False

async def add_contact(client: TelegramClient, user_id: int, first_name: str, last_name: str = "", phone: str = "") -> bool:
    """
    Додає користувача до контактів через username або ID.
    """
    try:
        print(f"[DEBUG] Початок додавання контакту для user_id={user_id}")

        # Спробуємо отримати інформацію про користувача
        try:
            user = await client.get_entity(user_id)
            print(f"[DEBUG] Отримано інформацію про користувача: @{user.username}, ім'я: {getattr(user, 'first_name', 'N/A')}")
        except Exception as e:
            print(f"[ERROR] Не вдалося отримати інформацію про користувача {user_id}: {e}")
            return False

        # Якщо є username - використовуємо його для додавання контакту
        if user.username:
            print(f"[DEBUG] Додавання контакту через username: @{user.username}")

            # Використовуємо AddContactRequest замість ImportContactsRequest
            from telethon.tl.functions.contacts import AddContactRequest
            from telethon.tl.types import InputUser

            # Створюємо InputUser з username
            input_user = await client.get_input_entity(user.username)

            # Обробляємо ім'я
            first_name = (getattr(user, 'first_name', '') or '').strip()
            last_name = (getattr(user, 'last_name', '') or '').strip()

            # Очищаємо ім'я від спеціальних символів
            def clean_name(name: str) -> str:
                if not name:
                    return ""
                import re
                name = re.sub(r'[^\w\s\-_]', '', name)
                return name[:50] if name else ""

            first_name = clean_name(first_name)
            last_name = clean_name(last_name)

            if not first_name:
                first_name = user.username

            print(f"[DEBUG] Додавання контакту: first_name='{first_name}', last_name='{last_name}'")

            result = await client(AddContactRequest(
                id=input_user,
                first_name=first_name,
                last_name=last_name,
                phone="",  # Порожній телефон
                add_phone_privacy_exception=False
            ))

            if result:
                print(f"[SUCCESS] Контакт @{user.username} доданий до адресної книги!")
                return True
            else:
                print(f"[WARN] Не вдалося додати контакт @{user.username}")
                return False

        else:
            print(f"[WARN] Користувач {user_id} не має username - неможливо додати до контактів без номера телефону")
            return False

    except Exception as e:
        print(f"[ERROR] Помилка додавання контакту для user_id={user_id}: {str(e)}")
        print(f"[ERROR] Тип помилки: {type(e).__name__}")
        import traceback
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        return False

async def get_contacts_list(client: TelegramClient) -> set[int]:
    """
    Отримує список ID всіх контактів користувача.
    """
    try:
        print("[DEBUG] Отримання списку контактів...")
        contacts = await client(GetContactsRequest(hash=0))
        contact_ids = set()
        for user in contacts.users:
            contact_ids.add(user.id)
        print(f"[DEBUG] Отримано {len(contact_ids)} контактів з Telegram API")
        return contact_ids
    except Exception as e:
        print(f"[ERROR] Не вдалося отримати список контактів: {e}")
        return set()

async def is_contact_exists(client: TelegramClient, user_id: int, contacts_cache: set[int] = None) -> bool:
    """
    Перевіряє, чи є користувач у контактах.
    Використовує кеш для оптимізації, якщо передано.
    """
    if contacts_cache is not None:
        return user_id in contacts_cache

    # Якщо кеша немає - отримуємо список контактів
    contacts = await get_contacts_list(client)
    return user_id in contacts