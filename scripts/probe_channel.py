"""Отладка: сообщения канала по id, закреп, описание, ссылки-приглашения."""
import asyncio, base64, json, os, sys
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import CheckChatInviteRequest
from telethon.tl.functions.channels import GetFullChannelRequest
from login import load_session


def pack(m):
    btns = []
    if m.reply_markup and getattr(m.reply_markup, "rows", None):
        for row in m.reply_markup.rows:
            for b in row.buttons:
                btns.append({"text": getattr(b, "text", ""), "url": getattr(b, "url", None)})
    return {"id": m.id, "date": str(m.date), "edit": str(m.edit_date or ""), "text": m.message or "",
            "buttons": btns, "links": [getattr(e, "url", None) for e in (m.entities or []) if getattr(e, "url", None)]}


async def main():
    c = TelegramClient(StringSession(load_session()), int(os.environ["TG_API_ID"]), os.environ["TG_API_HASH"])
    await c.connect()
    out = {}
    ent = await c.get_entity("BigSaleApple")
    full = await c(GetFullChannelRequest(ent))
    out["about"] = full.full_chat.about
    out["pinned"] = full.full_chat.pinned_msg_id
    out["linked_chat"] = getattr(full.full_chat, "linked_chat_id", None)
    ids = [11510, 12064, 12918, 12919, 12967, full.full_chat.pinned_msg_id or 0]
    msgs = await c.get_messages(ent, ids=ids)
    out["by_id"] = [pack(m) if m else None for m in msgs]
    out["newest"] = [pack(m) for m in await c.get_messages(ent, limit=15)]
    for h in ("6CP_wv6m3Os2NzEy", "Abfsk6RrTLNkYzky"):
        try:
            inv = await c(CheckChatInviteRequest(h))
            chat = getattr(inv, "chat", None)
            out[h] = {"title": getattr(inv, "title", None) or getattr(chat, "title", None),
                      "member": chat is not None, "count": getattr(inv, "participants_count", None)}
            if chat is not None:
                out[h]["posts"] = [pack(m) for m in await c.get_messages(chat, limit=200)]
        except Exception as e:
            out[h] = {"error": str(e)}
    await c.disconnect()
    blob = base64.b64encode(json.dumps(out, ensure_ascii=False).encode()).decode()
    for i in range(0, len(blob), 4000):
        print("B64 " + blob[i:i + 4000])


asyncio.run(main())
