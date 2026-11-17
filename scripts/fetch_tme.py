"""Тексты постов публичного канала через веб-версию t.me/s/<канал> (видны и новые типы постов)."""
import base64, json, re, sys, time, urllib.request
from bs4 import BeautifulSoup

ch = sys.argv[1]
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36"}
out, before, seen = {}, None, set()
for page in range(80):
    url = f"https://t.me/s/{ch}" + (f"?before={before}" if before else "")
    html = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read().decode("utf-8", "ignore")
    soup = BeautifulSoup(html, "html.parser")
    msgs = soup.select("div.tgme_widget_message[data-post]")
    if not msgs:
        break
    ids = []
    for m in msgs:
        pid = int(m["data-post"].split("/")[-1])
        ids.append(pid)
        t = m.select_one("div.tgme_widget_message_text")
        if not t:
            continue
        for br in t.find_all("br"):
            br.replace_with("\n")
        for img in t.find_all("img"):            # эмодзи-картинки → их alt
            img.replace_with(img.get("alt", ""))
        tm = m.select_one("time[datetime]")
        out[pid] = {"id": pid, "date": tm["datetime"] if tm else "", "text": t.get_text()}
    new_before = min(ids)
    if new_before in seen:
        break
    seen.add(new_before)
    before = new_before
    time.sleep(1)
posts = sorted(out.values(), key=lambda p: -p["id"])
print("POSTS", len(posts), "min id", before)
blob = base64.b64encode(json.dumps(posts, ensure_ascii=False).encode()).decode()
for i in range(0, len(blob), 4000):
    print("B64 " + blob[i:i + 4000])
