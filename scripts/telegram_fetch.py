"""Забирает прайсовые посты закрытого канала через Telegram API (Telethon).

Секреты берутся из переменных окружения (GitHub Secrets):
  TG_API_ID, TG_API_HASH  — ключи приложения с my.telegram.org
  TG_SESSION_KEY          — ключ шифрования сессии (сама сессия — data/session.enc, см. login.py)
  TG_CHANNEL_INVITE       — хеш ссылки-приглашения (часть после t.me/+)
"""
import asyncio
import os

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import CheckChatInviteRequest

LOOKBACK = 600  # постов назад: прайсовые посты старые, но каждый день редактируются


async def fetch_posts():
    from login import load_session
    client = TelegramClient(StringSession(load_session()),
                            int(os.environ["TG_API_ID"]), os.environ["TG_API_HASH"])
    await client.connect()
    if not await client.is_user_authorized():
        raise SystemExit("Сессия Telegram недействительна — запустите вход заново (workflow «Вход в Telegram»).")
    invite = await client(CheckChatInviteRequest(os.environ["TG_CHANNEL_INVITE"]))
    chat = getattr(invite, "chat", None)
    if chat is None:
        raise SystemExit("Аккаунт не состоит в канале — вступите в канал по ссылке.")
    posts = []
    async for msg in client.iter_messages(chat, limit=LOOKBACK):
        if msg.message:
            posts.append((msg.id, msg.edit_date or msg.date, msg.message))
    await client.disconnect()
    # свежие правки первыми: при повторах позиций побеждает последняя версия
    posts.sort(key=lambda p: p[1], reverse=True)
    return [text for _, _, text in posts]


def get_posts():
    return asyncio.run(fetch_posts())
