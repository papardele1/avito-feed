"""Фото для объявлений: берём с atomm.store, переводим в JPEG (Авито не принимает WebP).

1. Скачиваем каталог сайта (catalog.json) и карту фото (img/index.json).
2. Для каждой позиции прайса ищем товар сайта той же модели и цвета (память не важна —
   фото одинаковые).
3. Фото конвертируем в JPEG и кладём в docs/img/<hash>.jpg — Авито забирает их по
   прямой ссылке из публичного репозитория. Уже скачанные фото повторно не качаются.
"""
import hashlib
import io
import json
import re
import urllib.request
from pathlib import Path

SITE = "https://atomm.store"
ROOT = Path(__file__).resolve().parent.parent
IMG_DIR = ROOT / "docs" / "img"
RAW_BASE = "https://raw.githubusercontent.com/papardele1/avito-feed/main/docs/img/"

# слова, отличающие модели друг от друга: если такое слово есть только с одной стороны — это другая модель
DISCRIM = {"pro", "max", "plus", "ultra", "mini", "air", "fe", "lite", "e", "se", "edge", "fold", "flip",
           "neo", "xl", "a", "s", "t", "duo", "classic", "gen", "slim", "power", "x", "go",
           "мини", "про", "лайт", "макс", "стрит"}
NOISE = {"телефон", "смартфон", "планшет", "ноутбук", "часы", "умные", "беспроводные", "наушники", "цвет",
         "гб", "тб", "gb", "tb", "esim", "sim", "nano", "электронная", "карта", "wi", "fi", "wifi",
         "сотовая", "связь", "cellular", "lte", "новый", "для", "с", "и", "мм", "mm", "размер", "корпус",
         "ремешок", "версия", "5g", "4g", "global", "eac", "ростест"}


def get(url, binary=False, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "atomm-avito-feed/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    return data if binary else data.decode("utf-8")


def tokens(s):
    s = s.lower().replace("ё", "е")
    for a, b in SYN:
        s = re.sub(a, b, s)
    s = re.sub(r"\b[45]g\b", " ", s)                         # 5G/4G не отличают модель
    s = re.sub(r"(\d+)\s*(гб|тб|gb|tb)\b", " ", s)          # память не учитываем
    s = re.sub(r"\b\d+\s*/\s*\d+\b", " ", s)                 # 12/256
    s = re.sub(r"([a-z])(\d)", r"\1 \2", s)                   # watch8 → watch 8
    s = re.sub(r"(\d)([a-z])", r"\1 \2", s)                   # 17e → 17 e, 10a → 10 a
    return [t for t in re.findall(r"[a-zа-я0-9+]+", s) if t not in NOISE]


# Наши (английские) цвета → слова, которыми сайт пишет цвет по-русски
COLOR_RU = {
    "black": "черный черная черные", "white": "белый белая белые", "silver": "серебристый серебристая",
    "blue": "синий синяя голубой голубая", "gray": "серый серая", "grey": "серый серая", "gold": "золотой золотистый",
    "turquoise": "бирюзовый бирюзовая", "lilac": "лиловый лиловая сиреневый", "coral": "коралловый кораллово",
    "starlight": "сияющая звезда", "midnight": "темная ночь полночь", "space": "космос космический",
    "purple": "фиолетовый фиолетовая пурпурный", "pink": "розовый розовая", "green": "зеленый зеленая",
    "yellow": "желтый желтая", "orange": "оранжевый", "red": "красный", "sky": "небесно голубой",
    "lavender": "лавандовый", "teal": "бирюзовый", "titanium": "титан", "natural": "натуральный",
    "desert": "пустынный", "graphite": "графитовый", "cream": "кремовый", "navy": "темно синий",
}
SECTIONS = {  # категория Авито → разделы каталога сайта
    "Телефоны": {0, 3}, "Планшеты и электронные книги": {1}, "Ноутбуки": {2}, "Аудио и видео": {4, 7},
    "Игры, приставки и программы": {5}, "Бытовая техника": {6}, "Фототехника": {7},
    "Товары для компьютера": {8, 2, 1},
}
SYN = [(r"\bs(1[0-9])\b", r"series \1"), (r"\bwatch\s?(\d)", r"watch \1")]


def color_words(s):
    """Английский цвет из скобок каталога: «цвет: черный (Black)» → {'black'}."""
    found = re.findall(r"\(([A-Za-z][A-Za-z /-]+)\)", s)
    return {w for f in found for w in tokens(f)}


def model_and_color(it, prof):
    """Модель (без цвета и памяти) и цвет позиции прайса."""
    color = (it.get("color_official") or it.get("color_src") or "").strip()
    if prof and prof.get("Model"):
        model = f"{prof.get('Vendor') or ''} {prof['Model']}"
    elif it.get("model"):
        model = it["model"]
    else:
        model = it["title"]
    return model, color


def build_index(catalog, img_index):
    out = []
    for row in catalog["items"]:
        iid, name = row[0], row[4]
        if iid not in img_index:
            continue
        base = re.sub(r"\(.*?\)", " ", name)
        out.append({"id": iid, "name": name, "file": img_index[iid], "sec": row[1],
                    "tok": set(tokens(base)), "color": color_words(name),
                    "ru": set(tokens(" ".join(re.findall(r"\(([^)]*[а-я][^)]*)\)", name.lower()))))})
    return out


COLORISH = set(COLOR_RU) | {"jet", "rose", "fog", "obsidian", "frost", "hibiscus", "pistachio", "canyon",
                            "olive", "ultramarine", "sage", "mist", "deep", "cosmic", "cloud", "light", "glacier",
                            "burgundy", "shadow", "violet", "lilac", "mint", "turquoise", "coral", "lagoon",
                            "dreamy", "chroma", "indigo", "sterling", "galactic", "cobalt", "starlit", "aurora",
                            "velvet", "silk", "infinite", "ultra violet", "camouflage", "neon", "satin", "pyrite",
                            "polished", "matte", "bronze", "loop", "alpine", "trail", "milanese", "band", "sport",
                            "ocean", "charcoal", "bright"}
SIZEISH = {"s", "m", "l", "2024", "2025", "2026", "mm", "lte", "wifi"}


def match(model, color, index, sections=None, generic=False):
    mt = set(tokens(model))
    ct = set(tokens(color))
    if generic:  # в названии есть и модель, и цвет, и размер ремешка — отделяем цвет
        ct |= mt & COLORISH
        mt -= COLORISH | SIZEISH
    if not mt:
        return None
    ru = set()
    for w in ct:
        ru |= set(COLOR_RU.get(w, "").split())
    best, best_score = None, 0
    for c in index:
        if sections and c["sec"] not in sections:
            continue
        have = c["tok"] | c["color"]
        cover = len(mt & have) / len(mt)
        if cover < 0.75:
            continue
        if {t for t in mt if t.isdigit()} - c["tok"]:   # цифры модели — строго (S11 ≠ S12)
            continue
        if ((c["tok"] - mt) | (mt - c["tok"])) & DISCRIM & (mt | c["tok"]) - (c["color"] if generic else set()):
            if (c["tok"] - mt) & DISCRIM or (mt - c["tok"]) & DISCRIM:
                continue
        score = 10 * cover - min(len(c["tok"] - mt), 9) * 0.3
        if ct:
            hit = len(ct & (c["color"] | c["tok"])) / len(ct)
            if ru and ru & (c["ru"] | c["tok"]):
                hit = max(hit, 0.8)
            if hit < 0.5:  # фото другого цвета не ставим
                continue
            score += 20 * hit
        if score > best_score:
            best, best_score = c, score
    return best


def to_jpeg(webp_bytes):
    from PIL import Image
    im = Image.open(io.BytesIO(webp_bytes))
    if im.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        im = im.convert("RGBA")
        bg.paste(im, mask=im.split()[-1])
        im = bg
    else:
        im = im.convert("RGB")
    if min(im.size) < 600:  # Авито любит фото от 600px — увеличиваем аккуратно
        k = 600 / min(im.size)
        im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def ensure_images(items, route):
    """Возвращает {image_key: [url]} и отчёт. route — функция категории из build_feed."""
    catalog = json.loads(get(SITE + "/catalog.json"))
    img_index = json.loads(get(SITE + "/img/index.json"))
    index = build_index(catalog, img_index)
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    result, matched, missed = {}, [], []
    for it in items:
        prof = route(it)
        if not prof:
            continue
        model, color = model_and_color(it, prof)
        key = image_key(it)
        if key in result:
            continue
        generic = not (prof.get("Model") or it.get("model"))
        c = match(model, color, index, SECTIONS.get(prof.get("Category")), generic)
        if not c:
            missed.append(f"{model} | {color}")
            continue
        fn = hashlib.sha1(c["file"].encode()).hexdigest()[:16] + ".jpg"
        path = IMG_DIR / fn
        if not path.exists():
            try:
                path.write_bytes(to_jpeg(get(f"{SITE}/img/{c['file']}", binary=True)))
            except Exception as e:  # noqa: BLE001 — одно фото не должно ронять прогон
                missed.append(f"{model} | {color} | ошибка загрузки: {e}")
                continue
        result[key] = [RAW_BASE + fn]
        matched.append(f"{it['title']}  →  {c['name']}")
    return result, matched, missed


def image_key(it):
    return f"{it.get('group') or it['title']}|{(it.get('color_src') or '').lower()}"
