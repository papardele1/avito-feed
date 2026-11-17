"""Ищет фото товаров на 2cent.ru и apple-avenue.ru по картам сайта (sitemap) → docs/img/cand/<slug>.jpg.
Запросы — data/photo_queries.json: [slug, match, exclude, query, (обязательные слова для адреса)]."""
import io, json, re, sys, time, urllib.request, gzip
from pathlib import Path
from PIL import Image

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
      "Accept-Language": "ru-RU,ru;q=0.9"}
OUT = Path("docs/img/cand"); OUT.mkdir(parents=True, exist_ok=True)


def get(url):
    data = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return data


def sitemap_urls(root):
    out, todo, seen = [], [root], set()
    while todo and len(seen) < 60:
        u = todo.pop()
        if u in seen:
            continue
        seen.add(u)
        try:
            x = get(u).decode("utf-8", "ignore")
        except Exception as e:
            print("sitemap err", u, e); continue
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", x)
        if "<sitemapindex" in x:
            todo += locs
        else:
            out += locs
    return out


COLOR = {"black": ["black", "chernyy", "chernyj", "chernaya", "chernye", "obsidian"],
         "white": ["white", "belyy", "belyj", "belaya", "belye"],
         "blue": ["blue", "siniy", "sinij", "goluboy", "golubaya"],
         "red": ["red", "krasnyy", "krasnyj", "krasnaya"],
         "green": ["green", "zelenyy", "zelenyj", "zelenaya"],
         "silver": ["silver", "serebristyy", "serebristyj"],
         "pink": ["pink", "rozovyy", "rozovyj"],
         "yellow": ["yellow", "zheltyy", "zheltyj"], "gold": ["gold", "zolotoy"],
         "brown": ["brown", "korichnevyy"], "gray": ["gray", "grey", "seryy", "seryj"]}


def toks(s):
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def ok(slug_t, word):
    alts = COLOR.get(word, [word])
    return any(a in slug_t for a in alts)


def main():
    items = json.loads(Path("data/photo_queries.json").read_text(encoding="utf-8"))
    only = set(sys.argv[1].split(",")) if len(sys.argv) > 1 and sys.argv[1] else None
    urls = []
    for root in ("https://2cent.ru/sitemap.xml", "https://apple-avenue.ru/sitemap.xml"):
        u = sitemap_urls(root)
        print("sitemap", root, len(u))
        urls += [x for x in u if re.search(r"/(product|catalog)/", x)]
    slugs = [(u, toks(u.rstrip("/").rsplit("/", 1)[-1].replace("_", "-"))) for u in urls]
    for it in items:
        slug, _m, _e, q = it[:4]
        need = it[4] if len(it) > 4 else [w for w in re.findall(r"[a-z0-9]+", q.lower())]
        excl = it[5] if len(it) > 5 else []
        if only and slug not in only:
            continue
        cands = [(u, t) for u, t in slugs if all(ok(t, w) for w in need) and not any(e in t for e in excl)]
        cands.sort(key=lambda c: (len(c[1]), "apple-avenue" in c[0]))
        if not cands:
            print("NONE", slug, need); continue
        u = cands[0][0]
        try:
            page = get(u).decode("utf-8", "ignore")
            m = re.search(r'(/storage/photo/resized/xy_866x866/[^"\'\s]+)', page)
            img = ("https://2cent.ru" + m.group(1)) if m else None
            if not img:
                m = re.search(r'property="og:image" content="([^"]+)"', page)
                img = m.group(1) if m else None
                if img and img.startswith("/"):
                    img = re.match(r"https?://[^/]+", u).group(0) + img
            if not img:
                print("NOIMG", slug, u); continue
            im = Image.open(io.BytesIO(get(img)))
            if im.mode in ("RGBA", "LA", "P"):
                im = im.convert("RGBA"); bg = Image.new("RGB", im.size, "white"); bg.paste(im, mask=im.split()[-1]); im = bg
            im.convert("RGB").save(OUT / f"{slug}.jpg", quality=92)
            print("OK", slug, im.size, u, "| alts:", " ".join(c[0].rsplit('/', 2)[-2] for c in cands[1:3]))
        except Exception as e:
            print("ERR", slug, u, e)
        time.sleep(1)


main()
