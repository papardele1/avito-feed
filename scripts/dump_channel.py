"""Печатает в лог посты публичного Telegram-канала (для сравнения прайсов). В репозиторий не пишет."""
import asyncio, base64, json, os, sys
from telethon import TelegramClient
from telethon.sessions import StringSession
from login import load_session


async def main(name, limit):
    c = TelegramClient(StringSession(load_session()), int(os.environ["TG_API_ID"]), os.environ["TG_API_HASH"])
    await c.connect()
    ent = await c.get_entity(name)
    out = []
    async for m in c.iter_messages(ent, limit=limit):
        if m.message:
            out.append({"id": m.id, "date": str(m.date), "edit": str(m.edit_date or ""), "text": m.message})
    await c.disconnect()
    blob = base64.b64encode(json.dumps(out, ensure_ascii=False).encode()).decode()
    print("POSTS", len(out))
    for i in range(0, len(blob), 4000):
        print("B64 " + blob[i:i + 4000])


asyncio.run(main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 400))
