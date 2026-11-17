"""Скачать картинку товара (og:image со страницы магазина или прямую ссылку) в docs/img/<name>.jpg."""
import io, re, sys, urllib.request
from PIL import Image

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read()


name, *urls = sys.argv[1:]
for i, url in enumerate(urls):
    try:
        data = get(url)
        try:
            Image.open(io.BytesIO(data)); is_img = True
        except Exception:
            is_img = False
        if not is_img:
            html = data.decode("utf-8", "ignore")
            m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', html) or \
                re.search(r'content=["\']([^"\']+)["\'][^>]+property=["\']og:image', html) or \
                re.search(r'(https?://[^"\'\s]+/media/catalog/product/[^"\'\s]+?\.(?:jpg|jpeg|png|webp))', html)
            if not m:
                print("нет картинки на странице:", url, len(html), html[:200].replace("\n", " ")); continue
            img_url = m.group(1).replace("&amp;", "&")
            print("og:image:", img_url)
            data = get(img_url)
        im = Image.open(io.BytesIO(data))
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA"); bg = Image.new("RGB", im.size, "white"); bg.paste(im, mask=im.split()[-1]); im = bg
        im = im.convert("RGB")
        out = f"docs/img/{name}_{i}.jpg"
        im.save(out, quality=92)
        print("сохранено", out, im.size)
    except Exception as e:
        print("ошибка", url, e)
