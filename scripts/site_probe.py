"""Отладка поиска фото на сайтах магазинов: печатает статус, заголовок, ссылки на товары и картинки."""
import re, sys, urllib.request, urllib.error, html as H

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
      "Accept-Language": "ru-RU,ru;q=0.9"}
for url in sys.argv[1:]:
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40)
        page = r.read().decode("utf-8", "ignore")
        st = r.status
    except urllib.error.HTTPError as e:
        page, st = e.read().decode("utf-8", "ignore"), e.code
    except Exception as e:
        print("ERR", url, e); continue
    t = re.search(r"<title>(.*?)</title>", page, re.S)
    print("==", st, url, "|", H.unescape(t.group(1).strip())[:100] if t else "", "| len", len(page))
    links = []
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page, re.S):
        href, txt = m.group(1), re.sub(r"<[^>]+>", " ", m.group(2))
        txt = H.unescape(re.sub(r"\s+", " ", txt)).strip()
        if re.search(r"/(product|catalog)/", href) and len(txt) > 8:
            links.append(f"{txt[:70]} -> {href}")
    for l in list(dict.fromkeys(links))[:12]:
        print("  L", l)
    og = re.search(r'property="og:image" content="([^"]+)"', page)
    print("  OG", og.group(1) if og else None)
    imgs = re.findall(r'(?:src|data-src)="([^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', page)
    for i in imgs[:5]:
        print("  I", i)
