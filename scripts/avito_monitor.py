"""Контроль Авито через API и отчёты в «Избранное» Telegram.

  report  — проверяет последний отчёт автозагрузки, пишет, если что-то изменилось или есть ошибки
  summary — сводка за день: просмотры, контакты, избранное, топ объявлений, баланс
"""
import asyncio, json, os, re, sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from avito_api import call

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "monitor_state.json"
MSK = timezone(timedelta(hours=3))


def titles():
    """ad_id → заголовок и цена из нашего фида."""
    x = (ROOT / "docs" / "avito.xml").read_text(encoding="utf-8")
    out = {}
    for ad in re.findall(r"<Ad>.*?</Ad>", x, re.S):
        i = re.search(r"<Id>(.*?)</Id>", ad).group(1)
        t = re.search(r"<Title>(.*?)</Title>", ad).group(1)
        out[i] = t
    return out


def leaves(root):
    """(раздел / подраздел, количество) из дерева section_stats."""
    for sec in root.get("sections") or []:
        subs = sec.get("sections") or []
        if not subs:
            yield (sec.get("title", ""),), sec.get("count", 0)
        for sub in subs:
            yield (sec.get("title", ""), sub.get("title", "")), sub.get("count", 0)


def send(text):
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from login import load_session

    async def go():
        c = TelegramClient(StringSession(load_session()), int(os.environ["TG_API_ID"]), os.environ["TG_API_HASH"])
        await c.connect()
        await c.send_message("me", text, link_preview=False)
        await c.disconnect()
    asyncio.run(go())


def load_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def report():
    st, r = call("GET", "/autoload/v2/reports?per_page=5")
    reps = [x for x in r.get("reports", []) if x.get("status") != "processing"]
    if not reps:
        print("нет завершённых отчётов")
        return
    rid = reps[0]["id"]
    st, rep = call("GET", f"/autoload/v3/reports/{rid}")
    stats = Counter()
    for path, cnt in leaves(rep.get("section_stats") or {}):
        stats[" / ".join(p for p in path if p)] += cnt
    # объявления с ошибками и предупреждениями
    names = titles()
    errors, warns = Counter(), Counter()
    err_ads = {}
    page, pages = 0, 1
    while page < pages and page < 20:
        st, it = call("GET", f"/autoload/v2/reports/{rid}/items?per_page=200&page={page}")
        pages = (it.get("meta") or {}).get("pages", 0)
        for item in it.get("items", []):
            for m in item.get("messages", []):
                d = (m.get("description") or m.get("title") or "").strip()[:150]
                if m.get("type") == "error":
                    errors[d] += 1
                    err_ads.setdefault(d, []).append(names.get(item.get("ad_id"), item.get("ad_id")))
                elif m.get("type") == "warning":
                    warns[d] += 1
        page += 1
    sig = json.dumps([rid if errors else None, sorted(stats.items()), sorted(errors.items())], ensure_ascii=False)
    state = load_state()
    if state.get("last_sig") == sig.replace(str(rid), "") or state.get("last_report") == rid:
        print("без изменений")
        return
    now_msk = datetime.now(MSK)
    night_only = set(stats) <= {"Не опубликовано / Прошла дата окончания размещения"} and not errors
    state.update(last_report=rid, last_sig=sig.replace(str(rid), ""))
    STATE.write_text(json.dumps(state))
    if night_only:
        print("ночное снятие по времени — не пишем")
        return
    lines = [f"📦 Авито, загрузка {now_msk:%d.%m %H:%M}"]
    for k, v in sorted(stats.items(), key=lambda kv: -kv[1]):
        lines.append(f"• {k}: {v}")
    if errors:
        lines.append("\n❗ Ошибки:")
        for d, n in errors.most_common(8):
            ex = ", ".join(err_ads[d][:3])
            lines.append(f"• {d} — {n} шт. (напр.: {ex})")
    if warns:
        lines.append(f"\n⚠️ Предупреждений: {sum(warns.values())} (не мешают публикации)")
    send("\n".join(lines))
    print("\n".join(lines))


def all_items():
    out, page = [], 1
    while page <= 30:
        st, r = call("GET", f"/core/v1/items?per_page=100&page={page}&status=active")
        res = r.get("resources", [])
        out += res
        if len(res) < 100:
            break
        page += 1
    return out


def summary():
    st, me = call("GET", "/core/v1/accounts/self")
    uid = me["id"]
    items = all_items()
    today = datetime.now(MSK).date().isoformat()
    totals, per = Counter(), []
    for i in range(0, len(items), 200):
        chunk = items[i:i + 200]
        st, r = call("POST", f"/stats/v1/accounts/{uid}/items", {
            "dateFrom": today, "dateTo": today, "itemIds": [x["id"] for x in chunk],
            "fields": ["uniqViews", "uniqContacts", "uniqFavorites"], "periodGrouping": "day"})
        title = {x["id"]: x.get("title", "") for x in chunk}
        for row in (r.get("result") or {}).get("items", []):
            s = Counter()
            for d in row.get("stats", []):
                for k in ("uniqViews", "uniqContacts", "uniqFavorites"):
                    s[k] += d.get(k, 0) or 0
            totals.update(s)
            per.append((title.get(row.get("itemId"), ""), s))
    st, bal = call("GET", f"/core/v1/accounts/{uid}/balance/")
    lines = [f"📊 Авито за {datetime.now(MSK):%d.%m}",
             f"Активных объявлений: {len(items)}",
             f"Просмотры: {totals['uniqViews']} · Контакты: {totals['uniqContacts']} · В избранное: {totals['uniqFavorites']}"]
    top = sorted(per, key=lambda p: (p[1]["uniqContacts"], p[1]["uniqViews"]), reverse=True)[:7]
    top = [p for p in top if p[1]["uniqViews"]]
    if top:
        lines.append("\nТоп за день (просмотры / контакты):")
        lines += [f"• {t} — {s['uniqViews']} / {s['uniqContacts']}" for t, s in top]
    if st == 200:
        lines.append(f"\n💰 Кошелёк: {bal.get('real', 0)} ₽, бонусы: {bal.get('bonus', 0)} ₽")
    send("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    {"report": report, "summary": summary}[sys.argv[1]]()
