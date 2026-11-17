"""Пробуем прочитать посты нового формата через Kurigram (свежий слой API), сессию берём из Telethon."""
import asyncio, base64, json, os, struct, sys
from telethon.sessions import StringSession
from login import load_session

ss = StringSession(load_session())
dc_id, auth_key = ss.dc_id, ss.auth_key.key


async def main():
    from telethon import TelegramClient
    tc = TelegramClient(StringSession(load_session()), int(os.environ["TG_API_ID"]), os.environ["TG_API_HASH"])
    await tc.connect()
    me = await tc.get_me()
    await tc.disconnect()
    from pyrogram import Client, __version__
    print("kurigram", __version__)
    sess = base64.urlsafe_b64encode(struct.pack(">BI?256sQ?", dc_id, int(os.environ["TG_API_ID"]), False, auth_key, me.id, False)).decode().rstrip("=")
    app = Client("k", session_string=sess, in_memory=True, api_id=int(os.environ["TG_API_ID"]), api_hash=os.environ["TG_API_HASH"])
    await app.start()
    ids = [int(x) for x in sys.argv[1].split(",")]
    msgs = await app.get_messages("BigSaleApple", ids)
    out = []
    for m in msgs:
        t = m.text or m.caption or ""
        out.append({"id": m.id, "len": len(t), "text": t, "media": str(m.media), "raw": str(m)[:600] if not t else ""})
    await app.stop()
    blob = base64.b64encode(json.dumps(out, ensure_ascii=False).encode()).decode()
    for i in range(0, len(blob), 4000):
        print("B64 " + blob[i:i + 4000])

asyncio.run(main())
