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


def full():
    """Полный отчёт за сегодня — печатает JSON в лог (в репозиторий не пишет: он публичный)."""
    st, me = call("GET", "/core/v1/accounts/self")
    uid = me["id"]
    today = datetime.now(MSK).date().isoformat()
    items = []
    for status in ("active", "old", "removed", "blocked", "rejected"):
        page = 1
        while page <= 30:
            st, r = call("GET", f"/core/v1/items?per_page=100&page={page}&status={status}")
            res = r.get("resources", [])
            items += [dict(x, _status=status) for x in res]
            if len(res) < 100:
                break
            page += 1
    out = {"date": today, "items_by_status": Counter(x["_status"] for x in items)}
    rows = []
    for i in range(0, len(items), 200):
        chunk = items[i:i + 200]
        st, r = call("POST", f"/stats/v1/accounts/{uid}/items", {
            "dateFrom": today, "dateTo": today, "itemIds": [x["id"] for x in chunk],
            "fields": ["uniqViews", "uniqContacts", "uniqFavorites"], "periodGrouping": "day"})
        out.setdefault("stats_status", []).append(st)
        info = {x["id"]: x for x in chunk}
        for row in (r.get("result") or {}).get("items", []):
            s = Counter()
            for d in row.get("stats", []):
                for k in ("uniqViews", "uniqContacts", "uniqFavorites"):
                    s[k] += d.get(k, 0) or 0
            x = info.get(row.get("itemId"), {})
            rows.append({"id": row.get("itemId"), "title": x.get("title"), "price": x.get("price"),
                         "category": (x.get("category") or {}).get("name"), **s})
    rows.sort(key=lambda r: (r["uniqViews"], r["uniqContacts"]), reverse=True)
    out["totals"] = dict(sum((Counter({k: r[k] for k in ("uniqViews", "uniqContacts", "uniqFavorites")}) for r in rows), Counter()))
    out["items_with_views"] = sum(1 for r in rows if r["uniqViews"])
    out["top"] = rows[:40]
    cat = Counter()
    for r in rows:
        cat[r["category"]] += r["uniqViews"]
    out["views_by_category"] = cat.most_common()
    # переписки за сегодня
    start = int(datetime.now(MSK).replace(hour=0, minute=0, second=0).timestamp())
    chats, offset = [], 0
    while offset < 500:
        st, r = call("GET", f"/messenger/v2/accounts/{uid}/chats?limit=100&offset={offset}&chat_types=u2i")
        cs = r.get("chats", [])
        chats += cs
        if len(cs) < 100:
            break
        offset += 100
    today_chats = [c for c in chats if (c.get("created") or 0) >= start or ((c.get("last_message") or {}).get("created") or 0) >= start]
    out["chats_total"] = len(chats)
    out["chats_today"] = len(today_chats)
    out["chats_new_today"] = sum(1 for c in chats if (c.get("created") or 0) >= start)
    out["chats_items"] = Counter((((c.get("context") or {}).get("value") or {}).get("title")) for c in today_chats).most_common(20)
    # расходы
    st, bal = call("GET", f"/core/v1/accounts/{uid}/balance/")
    out["balance"] = {"status": st, **(bal if isinstance(bal, dict) else {})}
    st, cpa = call("POST", "/cpa/v3/balanceInfo", {})
    out["cpa_balance"] = {"status": st, **(cpa if isinstance(cpa, dict) else {})}
    st, ops = call("POST", f"/core/v1/accounts/{uid}/operations_history/", {
        "dateTimeFrom": f"{today}T00:00:00", "dateTimeTo": f"{today}T23:59:59"})
    out["operations"] = {"status": st, "data": ops}
    print("FULLREPORT " + json.dumps(out, ensure_ascii=False, default=str))


def upload():
    """Запустить загрузку файла сейчас, не дожидаясь расписания Авито."""
    st, r = call("POST", "/autoload/v1/upload")
    print("upload:", st, json.dumps(r, ensure_ascii=False)[:300])


if __name__ == "__main__":
    {"report": report, "summary": summary, "upload": upload, "full": full}[sys.argv[1]]()
