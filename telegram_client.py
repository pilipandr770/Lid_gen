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
    Додає користувача до контактів.
    Якщо номер телефону невідомий, використовує ім'я як ідентифікатор.
    """
    try:
        # Обробляємо None значення
        first_name = first_name or ""
        last_name = last_name or ""
        phone = phone or ""

        # Створюємо повне ім'я
        full_name = f"{first_name} {last_name}".strip()
        if not full_name:
            full_name = f"User_{user_id}"

        # Якщо є номер телефону - використовуємо його
        if phone and phone.startswith('+'):
            contact = InputPhoneContact(
                client_id=0,
                phone=phone,
                first_name=first_name,
                last_name=last_name
            )
            result = await client(ImportContactsRequest([contact]))
            if result.imported:
                print(f"[SUCCESS] Контакт '{full_name}' доданий з номером {phone}")
                return True
        else:
            # Якщо номера немає - просто позначаємо як контакт через ім'я
            # Це створить "тимчасовий" контакт без номера
            contact = InputPhoneContact(
                client_id=user_id,
                phone="",  # Порожній номер
                first_name=first_name or full_name,
                last_name=last_name
            )
            result = await client(ImportContactsRequest([contact]))
            if result.imported:
                print(f"[SUCCESS] Контакт '{full_name}' доданий як тимчасовий")
                return True

        print(f"[WARN] Не вдалося додати контакт '{full_name}'")
        return False

    except Exception as e:
        full_name = f"{first_name or ''} {last_name or ''}".strip() or f"User_{user_id}"
        print(f"[ERROR] Помилка додавання контакту '{full_name}': {e}")
        return False

async def get_contacts_list(client: TelegramClient) -> set[int]:
    """
    Отримує список ID всіх контактів користувача.
    """
    try:
        contacts = await client(GetContactsRequest(hash=0))
        contact_ids = set()
        for user in contacts.users:
            contact_ids.add(user.id)
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