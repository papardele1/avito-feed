"""Разбор прайса канала «Apple ОПТ/В розницу» в позиции для Авито.

Вход: текстовые файлы прайса (строки «Название - цена»), секции начинаются с ##.
Выход: items.json и items.csv с ценой поставщика и ценой +3,5%.
"""
import csv
import hashlib
import json
import math
import re
import sys
from pathlib import Path

MARKUP = 0.02
ROUND_TO = 100  # округление вверх до 100 ₽

COLOR_RU = {
    "black": "Чёрный", "jet black": "Чёрный", "jetblack": "Чёрный", "midnight": "Чёрный",
    "night sky": "Чёрный", "space black": "Чёрный", "infinite black": "Чёрный", "obsidian": "Чёрный",
    "graphite": "Тёмно-серый", "space gray": "Серый", "gray": "Серый", "grey": "Серый",
    "white": "Белый", "star white": "Белый", "starlight": "Белый", "snow": "Белый", "cream": "Бежевый",
    "silver": "Серебристый", "silver shadow": "Серебристый", "whitesilver": "Серебристый", "frost": "Белый",
    "blue": "Синий", "sky blue": "Голубой", "light blue": "Голубой", "ice blue": "Голубой", "iceblue": "Голубой",
    "icyblue": "Голубой", "ultramarine": "Синий", "navy": "Синий", "deep blue": "Синий", "blue shadow": "Синий",
    "blueberry": "Синий", "cobalt violet": "Фиолетовый", "violet": "Фиолетовый", "violet shadow": "Фиолетовый",
    "lavender": "Фиолетовый", "lavander": "Фиолетовый", "lilac": "Фиолетовый", "purple": "Фиолетовый",
    "ultra violet": "Фиолетовый", "glacier": "Голубой", "teal": "Бирюзовый", "turquoise": "Бирюзовый",
    "gold": "Золотистый", "desert": "Бежевый", "natural": "Серый", "orange": "Оранжевый", "burgundy": "Красный",
    "pink": "Розовый", "blush": "Розовый", "hibiscus": "Розовый", "yellow": "Жёлтый", "green": "Зелёный",
    "sage": "Зелёный", "mint": "Зелёный", "pistachio": "Зелёный", "pistacho": "Зелёный", "olive": "Зелёный",
    "starlit green": "Зелёный", "aurora green": "Зелёный", "green shadow": "Зелёный", "green silk": "Зелёный",
    "black velvet": "Чёрный", "canyon": "Коричневый", "fog": "Серый", "sky": "Голубой", "coral red": "Красный",
}

SECTION_RULES = [
    # (ключ секции, категория Авито, вид товара)
    ("iPhone", "Телефоны", "Мобильные телефоны"),
    ("iPad", "Планшеты и электронные книги", "Планшеты"),
    ("MacBook", "Ноутбуки", "Ноутбуки"),
]


def parse_line(line):
    line = line.strip()
    if not line or line.startswith("##"):
        return None
    m = re.match(r"^(.*?)\s*[-–—]\s*(\d[\d ]{2,})\s*(\(.*\))?\s*$", line)
    if not m:
        return None
    name = m.group(1).strip()
    price = int(m.group(2).replace(" ", ""))
    tail = (m.group(3) or "").strip("() ")
    return name, price, tail


def norm_mem(s):
    s = s.upper().replace("ТB", "TB")
    if s.endswith("TB"):
        return s[:-2] + " ТБ"
    return s.replace("GB", "") + " ГБ"


def sim_type(tail, name):
    t = (tail + " " + name).lower().replace(" ", "")
    if "esim+esim" in t:
        return "Только eSIM"
    if "sim+esim" in t:
        return "SIM + eSIM"
    if t.endswith("(esim)") or tail.strip().lower() == "esim":
        return "Только eSIM"
    if "2sim" in t:
        return "2 SIM"
    return ""


def color_ru(c):
    key = c.lower().strip()
    return COLOR_RU.get(key, "")


def our_price(p):
    return int(math.ceil(p * (1 + MARKUP) / ROUND_TO) * ROUND_TO)


def stable_id(*parts):
    raw = "|".join(parts).lower()
    return "ATM-" + hashlib.md5(raw.encode()).hexdigest()[:10]


IPHONE_RE = re.compile(
    r"^(?P<model>Duo|Air|\d{2}[eе]?(?: Plus| Pro Max| Pro| Prо)?)\s+(?P<mem>\d+(?:Tb|TB|ТБ)?)\s+(?P<color>.+?)$",
    re.I,
)


def parse_iphone(name, price, tail):
    m = IPHONE_RE.match(name)
    if not m:
        return None
    model = m.group("model").replace("е", "e").replace("Prо", "Pro")
    mem = m.group("mem")
    mem = mem if mem.lower().endswith("tb") else mem + "GB"
    color = m.group("color").strip()
    sim = sim_type(tail, name)
    if model == "Duo":
        full = "iPhone Duo"
    elif model == "Air":
        full = "iPhone Air"
    else:
        full = "iPhone " + model
    if not sim:
        sim = "SIM + eSIM"  # для 16/15/14 без пометки — стандартная версия
        sim_note = "по умолчанию"
    else:
        sim_note = ""
    mem_ru = norm_mem(mem)
    sim_short = {"SIM + eSIM": "SIM+eSIM", "Только eSIM": "eSIM", "2 SIM": "2 SIM"}[sim]
    title = f"{full} {mem_ru.replace(' ', '')} {color} {sim_short}"
    return {
        "brand": "Apple", "category": "Телефоны", "goods_type": "Мобильные телефоны",
        "model": full, "memory": mem_ru, "color_src": color, "color": color_ru(color),
        "sim": sim, "sim_note": sim_note, "title": title,
        "group": full,
    }


IPAD_RE = re.compile(
    r"^(?:iPad )?(?P<line>iPad 11|Air 1[13] M\d|Pro 1[13] M\d|11)\s+(?P<mem>\d+)\s+(?P<color>.+?)\s+(?P<net>WIFI|WiFi|WIFi|LTE)$",
    re.I,
)


def parse_ipad(name, price, tail):
    m = IPAD_RE.match(name)
    if not m:
        return None
    line = m.group("line")
    if not line.lower().startswith("ipad"):
        line = "iPad " + line
    net = "Wi-Fi + Cellular" if m.group("net").upper() == "LTE" else "Wi-Fi"
    mem = norm_mem(m.group("mem") + "GB")
    color = m.group("color").strip()
    title = f"{line} {mem.replace(' ', '')} {color} {'LTE' if 'Cell' in net else 'Wi-Fi'}"
    return {
        "brand": "Apple", "category": "Планшеты и электронные книги", "goods_type": "Планшеты",
        "model": line, "memory": mem, "color_src": color, "color": color_ru(color),
        "sim": "", "net": net, "title": title, "group": line,
    }


MAC_RE = re.compile(
    r"^(?P<sku>[A-Z0-9]{5,10})\s+(?P<line>Neo 13|Air 1[35]|Pro 1[46])\s+(?P<color>[A-Za-z ]+?)\s*(?:Nano -t\s*)?\((?P<chip>[^,]+),\s*(?P<ram>\d+)GB,\s*(?P<ssd>\d+\s*[GT]B|\d+\s*ТB|\d+Tb)\s*\)",
    re.I,
)


def parse_mac(name, price, tail):
    m = MAC_RE.match(name.replace("ТB", "TB"))
    if not m:
        return None
    line = "MacBook " + m.group("line")
    chip = m.group("chip").strip()
    ssd = m.group("ssd").replace(" ", "").upper()
    ssd_ru = norm_mem(ssd)
    color = m.group("color").strip()
    nano = " Nano-texture" if "Nano" in name else ""
    title = f"{line} {chip} {m.group('ram')}/{ssd.replace('GB','')} {color}{nano}"
    return {
        "brand": "Apple", "category": "Ноутбуки", "goods_type": "Ноутбуки",
        "model": line, "chip": chip, "ram": m.group("ram") + " ГБ", "memory": ssd_ru,
        "color_src": color, "color": color_ru(color), "sku": m.group("sku"), "title": title,
        "group": f"{line} {chip}",
    }


# Остальные секции — общая категория по секции
GENERIC_SECTIONS = {
    "AirPods": ("Аудио и видео", "Наушники"),
    "Apple Watch": ("Телефоны", "Смарт-часы и фитнес-браслеты"),
    "Dyson": ("Бытовая техника", "Для ухода за собой / пылесосы"),
    "Адаптеры": ("Телефоны", "Аксессуары"),
    "Samsung": ("Телефоны", "Мобильные телефоны"),
    "Google": ("Телефоны", "Мобильные телефоны"),
    "Honor": ("Телефоны", "Мобильные телефоны"),
    "Консоли": ("Игры, приставки и программы", "Игровые приставки"),
    "Камеры": ("Фототехника", "Компактные фотоаппараты / экшн-камеры"),
    "Умные очки": ("Аудио и видео", "Умные очки"),
    "Яндекс": ("Аудио и видео", "Умные колонки"),
    "Garmin": ("Телефоны", "Смарт-часы и фитнес-браслеты"),
    "Чехлы": ("Телефоны", "Аксессуары"),
}

PHONE_MEM_ONLY_RE = re.compile(r"(?<=\s)(?P<mem>64|128|256|512|1TB)(?=\s)", re.I)
PHONE_MEM_RE = re.compile(r"\b(?P<ram>\d{1,2})/(?P<mem>\d{2,4}|1TB)\b", re.I)


def generic_category(section, name):
    low = name.lower()
    for key, val in GENERIC_SECTIONS.items():
        if section.startswith(key) or key.lower() in section.lower():
            cat, gt = val
            break
    else:
        cat, gt = ("Прочее", "")
    # уточнения внутри смешанных секций
    if section.startswith("Samsung") or section.startswith("Google") or section.startswith("Honor"):
        if "tab " in low:
            return "Планшеты и электронные книги", "Планшеты"
        if "buds" in low or "powerbeats" in low:
            return "Аудио и видео", "Наушники"
        if "watch" in low or "ring" in low:
            return "Телефоны", "Смарт-часы и фитнес-браслеты"
        return "Телефоны", "Мобильные телефоны"
    if section.startswith("AirPods"):
        if "keyboard" in low or "mouse" in low or "pencil" in low:
            return "Товары для компьютера", "Клавиатуры, мыши, стилусы"
        if "whoop" in low:
            return "Телефоны", "Смарт-часы и фитнес-браслеты"
    if section.startswith("Адаптеры") and "ssd" in low:
        return "Товары для компьютера", "Накопители"
    return cat, gt


def parse_generic(section, name, price, tail):
    cat, gt = generic_category(section, name)
    item = {"brand": name.split()[0], "category": cat, "goods_type": gt, "model": "",
            "memory": "", "color_src": "", "color": "", "sim": "", "title": name}
    m = PHONE_MEM_RE.search(name) or PHONE_MEM_ONLY_RE.search(name)
    if m and gt in ("Мобильные телефоны", "Планшеты") and "watch" not in name.lower():
        mem = m.group("mem")
        if m.groupdict().get("ram"):
            item["ram"] = m.group("ram") + " ГБ"
        item["memory"] = norm_mem(mem if mem.upper().endswith("TB") else mem + "GB")
        item["model"] = name[: m.start()].strip()
        rest = name[m.end():].strip()
        rest = re.sub(r"\bSM-[A-Z0-9/]+\b", "", rest).strip()
        rest = re.sub(r"\(.*?\)", "", rest).strip()
        rest = re.sub(r"\b(?:WIFI|5G|Slim)\b", "", rest, flags=re.I).strip()
        item["color_src"] = rest
        item["color"] = color_ru(rest)
        item["group"] = item["model"]
        if gt == "Мобильные телефоны":
            item["sim"] = "2 SIM" if "/DS" in name else ""
    return item


def short_title(t):
    t = re.sub(r"\bSM-[A-Z0-9/]+\b", "", t)
    t = re.sub(r"\b010-\d{5}-\d{2}\b", "", t)
    t = re.sub(r"\b(?:RW4014|OPWWE262|M[A-Z0-9]{4}\d?)\b", "", t)
    t = re.sub(r"\((?:2 ревизия, )?", "(", t)
    t = re.sub(r"\s*\((?:распакован|оригинал|с кейсом)\)", "", t)
    t = re.sub(r"\s+", " ", t).replace("( ", "(").strip()
    if len(t) <= 50:
        return t
    for a, b in [("PITAKA Edge iPhone 17 Pro Max / 18 Pro Max", "PITAKA Edge 17/18 Pro Max"),
                 ("PITAKA Edge iPhone 17 Pro / 18 Pro", "PITAKA Edge 17/18 Pro"),
                 ("Happiness Rides In", "Happiness"), ("Monogram Leaping", "Monogram"),
                 ("Apple Watch ", "Watch "), ("Black Black", "Black"), ("Transitions", "Trans."),
                 ("Transparent", "Transp."), ("Ray-Ban Meta Wayfarer", "Ray-Ban Meta Wayfarer"),
                 ("Shiny Black G15 Green Polar", "Black G15 Polar"),
                 (" Gimbal Camera", ""), ("Nano-texture", "Nano"), (" Optics", "")]:
        t = t.replace(a, b)
    if len(t) <= 50:
        return t
    t = re.sub(r"\s*\(.*?\)", "", t).strip()
    while len(t) > 50 and " " in t:
        t = t.rsplit(" ", 1)[0]
    return t.rstrip(" /,-")


def section_kind(header):
    h = header.lower()
    if "iphone" in h:
        return "iphone"
    if h.startswith("##72902") or "ipad" in h:
        return "ipad"
    if "macbook" in h:
        return "mac"
    return "generic"


def run(files=(), text=None):
    items, errors = [], []
    sources = [Path(f).read_text(encoding="utf-8") for f in files]
    if text is not None:
        sources.append(text)
    for src in sources:
        section, kind = "", "generic"
        for raw in src.splitlines():
            if raw.startswith("##"):
                section = raw[2:].strip()
                kind = section_kind(raw)
                continue
            parsed = parse_line(raw)
            if not parsed:
                if raw.strip():
                    errors.append(raw)
                continue
            name, price, tail = parsed
            if kind == "iphone":
                it = parse_iphone(name, price, tail)
            elif kind == "ipad":
                it = parse_ipad(name, price, tail)
            elif kind == "mac":
                it = parse_mac(name, price, tail)
            else:
                it = parse_generic(section, name, price, tail)
            if not it and kind in ("ipad", "mac"):
                it = parse_generic("AirPods", name, price, tail)
            if not it:
                errors.append(raw)
                continue
            it["section"] = section
            it["source_line"] = raw.strip()
            it["supplier_price"] = price
            it["price"] = our_price(price)
            it["id"] = stable_id(it["source_line"].rsplit(" - ", 1)[0], it.get("sim", ""))
            it["title"] = short_title(it["title"])
            items.append(it)
    return items, errors


if __name__ == "__main__":
    out = Path(sys.argv[1])
    files = sys.argv[2:]
    items, errors = run(files)
    ids = [i["id"] for i in items]
    dup = {x for x in ids if ids.count(x) > 1}
    out.mkdir(parents=True, exist_ok=True)
    (out / "items.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    cols = ["id", "section", "category", "goods_type", "brand", "model", "memory", "color_src",
            "color", "sim", "title", "supplier_price", "price", "source_line"]
    with open(out / "items.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(items)
    print(f"items: {len(items)}  errors: {len(errors)}  dup ids: {len(dup)}")
    for e in errors:
        print("  НЕ РАЗОБРАНО:", e)
    for d in dup:
        print("  ДУБЛЬ:", [i["source_line"] for i in items if i["id"] == d])
