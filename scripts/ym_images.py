"""Фото-кандидаты с Яндекс Маркета: первая картинка поиска (og:image) для каждого запроса → docs/img/cand/<slug>.jpg."""
import io, json, re, sys, time, urllib.parse, urllib.request
from pathlib import Path
from PIL import Image

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
      "Accept-Language": "ru-RU,ru;q=0.9"}
OUT = Path("docs/img/cand")
OUT.mkdir(parents=True, exist_ok=True)
items = json.loads(Path("data/photo_queries.json").read_text(encoding="utf-8"))
only = set(sys.argv[1].split(",")) if len(sys.argv) > 1 and sys.argv[1] else None


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read()


for slug, _m, _e, q in items:
    if only and slug not in only:
        continue
    try:
        page = get("https://market.yandex.ru/search?text=" + urllib.parse.quote(q)).decode("utf-8", "ignore")
        m = re.search(r'"property","content":"([^"]*get-mpic[^"]*)"', page) or \
            re.search(r'og:image","content":"([^"]+)"', page)
        if not m:
            print("NO", slug, "len", len(page), "captcha" if "captcha" in page[:5000].lower() else ""); continue
        url = m.group(1)
        im = Image.open(io.BytesIO(get(url)))
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA"); bg = Image.new("RGB", im.size, "white"); bg.paste(im, mask=im.split()[-1]); im = bg
        im = im.convert("RGB")
        if max(im.size) > 1200:
            im.thumbnail((1200, 1200))
        im.save(OUT / f"{slug}.jpg", quality=90)
        print("OK", slug, im.size, url)
    except Exception as e:
        print("ERR", slug, e)
    time.sleep(2)
