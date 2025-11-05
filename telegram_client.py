import datetime as dt
from typing import List, Optional, Tuple
from telethon import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.contacts import ImportContactsRequest
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
        print(f"[WARN] Не вдалося перевірити аватарку для користувача {user_id}: {e}")
        return False

async def add_contact(client: TelegramClient, user_id: int, first_name: str, last_name: str = "", phone: str = "") -> bool:
    """
    Додає користувача до контактів.
    Якщо номер телефону невідомий, використовує ім'я як ідентифікатор.
    """
    try:
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
                print(f"[SUCCESS] Контакт {first_name} доданий з номером {phone}")
                return True
        else:
            # Якщо номера немає - просто позначаємо як контакт через ім'я
            # Це створить "тимчасовий" контакт без номера
            contact = InputPhoneContact(
                client_id=user_id,
                phone="",  # Порожній номер
                first_name=first_name,
                last_name=last_name
            )
            result = await client(ImportContactsRequest([contact]))
            if result.imported:
                print(f"[SUCCESS] Контакт {first_name} доданий як тимчасовий")
                return True

        print(f"[WARN] Не вдалося додати контакт {first_name}")
        return False

    except Exception as e:
        print(f"[ERROR] Помилка додавання контакту {first_name}: {e}")
        return False