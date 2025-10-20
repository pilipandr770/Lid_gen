import datetime as dt
from typing import List, Optional, Tuple
from telethon import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.types import Channel, ChannelParticipantsAdmins
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