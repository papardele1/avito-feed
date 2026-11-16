"""Одноразовый вход в Telegram для GitHub Actions — в два шага, без компьютера.

Шаг 1 (start):  python login.py start  — Telegram присылает код в приложение.
Шаг 2 (finish): python login.py finish — код из приложения вводится в форму запуска.

Промежуточное состояние и итоговая сессия хранятся в репозитории только
в зашифрованном виде (ключ — секрет TG_SESSION_KEY). Пароль двухэтапной
проверки, если он включён, берётся из секрета TG_2FA.
"""
import asyncio
import base64
import hashlib
import json
import os
import sys
from pathlib import Path

from cryptography.fernet import Fernet
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession

ROOT = Path(__file__).resolve().parent.parent
PENDING = ROOT / "data" / "login_pending.enc"
SESSION = ROOT / "data" / "session.enc"


def fernet():
    key = hashlib.sha256(os.environ["TG_SESSION_KEY"].encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def client(session=""):
    return TelegramClient(StringSession(session), int(os.environ["TG_API_ID"]), os.environ["TG_API_HASH"])


async def start(phone):
    c = client()
    await c.connect()
    sent = await c.send_code_request(phone)
    state = {"session": c.session.save(), "phone": phone, "hash": sent.phone_code_hash}
    PENDING.write_bytes(fernet().encrypt(json.dumps(state).encode()))
    await c.disconnect()
    kind = type(sent.type).__name__
    where = {
        "SentCodeTypeApp": "в приложение Telegram — чат «Telegram» с синей галочкой (не SMS)",
        "SentCodeTypeSms": "по SMS",
        "SentCodeTypeEmailCode": "на почту, привязанную к Telegram",
        "SentCodeTypeCall": "звонком",
        "SentCodeTypeFlashCall": "звонком (код — последние цифры номера)",
        "SentCodeTypeFragmentSms": "через Fragment",
        "SentCodeTypeSetUpEmailRequired": "Telegram требует сначала привязать почту",
    }.get(kind, kind)
    print(f"Код отправлен: {where}. Тип: {kind}")


async def finish(code):
    state = json.loads(fernet().decrypt(PENDING.read_bytes()))
    c = client(state["session"])
    await c.connect()
    try:
        await c.sign_in(state["phone"], code, phone_code_hash=state["hash"])
    except SessionPasswordNeededError:
        await c.sign_in(password=os.environ["TG_2FA"])
    me = await c.get_me()
    SESSION.write_bytes(fernet().encrypt(c.session.save().encode()))
    PENDING.unlink()
    await c.disconnect()
    print(f"Вход выполнен: {me.first_name}. Сессия сохранена в зашифрованном виде.")


def load_session():
    """Строка сессии для ежедневного прогона."""
    if os.environ.get("TG_SESSION"):
        return os.environ["TG_SESSION"]
    return fernet().decrypt(SESSION.read_bytes()).decode()


if __name__ == "__main__":
    if sys.argv[1] == "start":
        asyncio.run(start(os.environ["TG_PHONE"]))
    else:
        asyncio.run(finish(os.environ["TG_CODE"].strip()))
