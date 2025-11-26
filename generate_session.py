import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession
from dotenv import load_dotenv

load_dotenv()

api_id = os.getenv("TELEGRAM_API_ID")
api_hash = os.getenv("TELEGRAM_API_HASH")

if not api_id or not api_hash:
    print("Будь ласка, заповніть .env файл (TELEGRAM_API_ID та TELEGRAM_API_HASH)")
    exit(1)

async def main():
    print("=== Генератор StringSession для Render/Docker ===")
    async with TelegramClient(StringSession(), int(api_id), api_hash) as client:
        session_str = client.session.save()
        print("\nВаш рядок сесії (скопіюйте все між лапками):")
        print(f"\n{session_str}\n")
        print("Збережіть цей рядок як змінну оточення TELEGRAM_SESSION на Render.com")

if __name__ == "__main__":
    asyncio.run(main())
