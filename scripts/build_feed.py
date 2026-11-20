"""Сборка XML-фида автозагрузки Авито из позиций прайса (items.json).

Каждая позиция прайса — отдельное объявление. Объявления одной модели
склеиваются Авито в мультиобъявление (MultiItem=Да + одинаковая Model).
"""
import json
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from description import description as sales_description

ROOT = Path(__file__).resolve().parent.parent
ADDRESS = "Москва, Багратионовский проезд, 7к2"
SHOW_FROM, SHOW_TO = 9, 18  # объявления видны с 9:00 до 18:00 по Москве


def show_window(now=None):
    """Окно показа: сегодня 9–18, а после 18:00 — уже завтрашнее."""
    from datetime import datetime, timedelta, timezone
    msk = timezone(timedelta(hours=3))
    now = now or datetime.now(msk)
    day = now.date() if now.hour < SHOW_TO else now.date() + timedelta(days=1)
    fmt = "%Y-%m-%dT%H:%M:%S+03:00"
    begin = datetime(day.year, day.month, day.day, SHOW_FROM, tzinfo=msk)
    end = datetime(day.year, day.month, day.day, SHOW_TO, tzinfo=msk)
    return begin.strftime(fmt), end.strftime(fmt)
COUNTRY = "Китай"

EN_RU = {
    "black": "черный", "jet black": "черный", "jetblack": "черный", "midnight": "черный", "night sky": "черный",
    "space black": "черный", "obsidian": "черный", "infinite black": "черный", "black velvet": "черный",
    "white": "белый", "star white": "белый", "starlight": "белый", "snow": "белый", "frost": "голубой",
    "silver": "серебристый", "silver shadow": "серебристый", "whitesilver": "серебристый",
    "blue": "синий", "navy": "синий", "deep blue": "синий", "blue shadow": "синий", "blueberry": "синий",
    "ultramarine": "синий", "sky blue": "голубой", "light blue": "голубой", "ice blue": "голубой",
    "iceblue": "голубой", "icyblue": "голубой", "glacier": "голубой", "teal": "голубой",
    "gray": "серый", "grey": "серый", "space gray": "серый", "graphite": "серый", "natural": "серый", "fog": "серый",
    "gold": "золотистый", "desert": "золотистый", "cream": "бежевый",
    "orange": "оранжевый", "canyon": "оранжевый", "burgundy": "красный", "red": "красный",
    "pink": "розовый", "hibiscus": "розовый", "blush": "розовый",
    "lavender": "фиолетовый", "lavander": "фиолетовый", "lilac": "фиолетовый", "purple": "фиолетовый",
    "violet": "фиолетовый", "violet shadow": "фиолетовый", "cobalt violet": "фиолетовый", "ultra violet": "фиолетовый",
    "green": "зеленый", "sage": "зеленый", "mint": "зеленый", "pistachio": "зеленый", "pistacho": "зеленый",
    "olive": "зеленый", "starlit green": "зеленый", "coraled": "красный", "coral red": "красный", "aurora green": "зеленый", "green shadow": "зеленый",
    "green silk": "зеленый", "yellow": "желтый",
}

# Флажок у позиции в прайсе → «Версия смартфона» на Авито
REGION = {"EU": "EU", "US": "USA", "CN": "CN", "IN": "IND", "JP": "JP", "HK": "HK", "GB": "UK",
          "AE": "UAE", "RU": "Ростест (EAC)"}
REGION_TEXT = {"EU": "европейская", "US": "американская", "CN": "китайская", "IN": "индийская",
               "JP": "японская", "HK": "гонконгская", "GB": "британская", "AE": "ОАЭ", "KR": "корейская",
               "KZ": "казахстанская", "CA": "канадская", "RU": "Ростест"}

# Цвет для категорий со справочником «Чёрный/Белый…» (геймпады и т.п.)
RU_CAP = {"черный": "Чёрный", "белый": "Белый", "серый": "Серый", "синий": "Синий", "голубой": "Голубой",
          "серебристый": "Серебристый", "фиолетовый": "Фиолетовый", "красный": "Красный",
          "розовый": "Розовый", "зеленый": "Зелёный", "оранжевый": "Оранжевый", "бежевый": "Бежевый",
          "золотистый": "Золотистый", "желтый": "Жёлтый"}


def load_phone_catalog():
    cat = {}
    for line in (ROOT / "data" / "avito_phone_catalog.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        key, mems, colors, rams = line.split("#")
        vendor, model = key.split("|")
        cat[(vendor, model)] = {"mem": mems.split(","), "colors": colors.split(","), "ram": rams.split(",")}
    return cat


PHONES = load_phone_catalog()


def load_nested():
    """Вложенный справочник Авито: (vendor, model) → {память ГБ: {цвет: [оперативка]}}."""
    out = {}
    f = ROOT / "data" / "avito_phone_nested.txt"
    if not f.exists():
        return out
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        key, *mems = line.split("#")
        vendor, model = key.split("|")
        d = {}
        for m in mems:
            mem, colors = m.split(":", 1)
            d[f"{mem} ГБ"] = {c.split(">")[0]: [f"{r} ГБ" for r in c.split(">")[1].split(",")]
                             for c in colors.split("~")}
        out[(vendor, model)] = d
    return out


NESTED = load_nested()

# Ближайшие цвета, если точного нет в справочнике (по порядку)
NEAR = {"голубой": ["синий", "фиолетовый"], "синий": ["голубой", "фиолетовый", "черный"],
        "черный": ["серый", "синий", "темно-серый"], "серый": ["темно-серый", "черный", "серебристый"],
        "серебристый": ["белый", "серый"], "белый": ["серебристый", "бежевый"],
        "золотистый": ["бежевый", "желтый"], "бежевый": ["золотистый", "белый"],
        "фиолетовый": ["розовый", "синий"], "зеленый": ["серый"], "красный": ["оранжевый", "розовый"],
        "розовый": ["фиолетовый", "красный"], "оранжевый": ["красный", "золотистый"]}


def norm(s):
    s = s.lower().replace("galaxy", "").replace("5g", "").replace("4g", "")
    return re.sub(r"[^a-z0-9+]", "", s)


def match_phone(model_text):
    """«Samsung S26 Ultra» → ("Samsung", "Galaxy S26 Ultra")."""
    t = model_text.replace("POCO", "Poco").replace("MIX", "Mix")
    vendor = None
    for v, prefix in [("Apple", "iphone"), ("Samsung", "samsung"), ("Google", "google"),
                      ("Xiaomi", "xiaomi"), ("Xiaomi", "poco"), ("OnePlus", "oneplus"), ("Honor", "honor")]:
        if t.lower().startswith(prefix):
            vendor = v
            break
    if not vendor:
        return None, None
    body = re.sub(r"^(samsung|google|xiaomi|oneplus|honor)\s+", "", t, flags=re.I)
    nb = norm(body)
    best = None
    for (v, m) in PHONES:
        if v == vendor and norm(m) == nb:
            return v, m
        if v == vendor and norm(m).startswith(nb) and (best is None or len(m) < len(best)):
            best = m
    return vendor, best or body


def color_for(src, allowed):
    words = src.lower().replace("/", " ")
    words = re.sub(r"\b(slim|wifi|wi-fi|lte|5g)\b", "", words).strip()
    cand = EN_RU.get(words)
    if not cand:
        for k in sorted(EN_RU, key=len, reverse=True):
            if k in words:
                cand = EN_RU[k]
                break
    if not cand:
        return None
    if not allowed or cand in allowed:
        return cand
    for near in NEAR.get(cand, []):
        if near in allowed:
            return near
    return None


def mem_for(mem_ru, allowed):
    v = mem_ru.replace(" ТБ", "TB").replace(" ГБ", "")
    if v.endswith("TB"):
        v = str(int(v[:-2]) * 1024)
    val = f"{v} ГБ"
    return val if (not allowed or val in allowed) else None


def load_tablets():
    out = {}
    f = ROOT / "data" / "avito_tablets.txt"
    for line in f.read_text(encoding="utf-8").splitlines() if f.exists() else []:
        if line.strip():
            key, mems, sims, colors = line.split("#")
            out[tuple(key.split("|"))] = {
                "mem": {m.split(">")[0]: m.split(">")[1] for m in mems.split(",")},
                "sim": sims.split(","), "colors": colors.split(",")}
    return out


TABLETS = load_tablets()
TAB_COLOR = {"silver": "Серебряный", "gray": "Серый", "grey": "Серый", "space gray": "Серый",
             "graphite": "Серый", "blue": "Голубой", "sky blue": "Голубой", "pink": "Розовый",
             "yellow": "Жёлтый", "purple": "Фиолетовый", "starlight": "Золотой", "gold": "Золотой",
             "space black": "Чёрный", "black": "Чёрный", "coral red": "Красный", "coraled": "Красный",
             "red": "Красный"}
TAB_NEAR = {"Чёрный": ["Серый"], "Серый": ["Чёрный", "Серебряный"], "Серебряный": ["Серый"],
            "Золотой": ["Серебряный"], "Фиолетовый": ["Голубой"], "Голубой": ["Серый"]}


def tablet_params(it):
    """Бренд/модель/память/SIM/оперативка/цвет по справочнику Авито «Планшеты»."""
    src = it["source_line"].lower()
    m = it["model"]
    if m.startswith("iPad") or re.match(r"(air|pro|mini)\b", src):
        brand = "Apple"
        low = m.lower()
        if "mini" in low:
            model = "iPad mini (2026)"
        elif "pro" in low:
            model = "iPad Pro 13 (2025)" if " 13" in low else "iPad Pro 11 (2025)"
        elif "air" in low:
            year = "2025" if "m3" in low else "2026"
            model = f"iPad Air {'13' if ' 13' in low else '11'} ({year})"
        else:
            model = "iPad 11 (2025)"
        cellular = bool(re.search(r"lte|cellular|5g|\bsim", src))
    else:
        brand = "Samsung"
        body = re.sub(r"^samsung\s+(galaxy\s+)?tab\s+", "", m, flags=re.I)
        cellular = bool(re.search(r"\b(5g|lte)\b", body, re.I))
        body = re.sub(r"\s+(5g|lte)\b", "", body, flags=re.I)
        body = re.sub(r"\s*\+\s*", "+", body).strip()
        model = "Galaxy Tab " + body
    info = TABLETS.get((brand, model))
    if not info:
        return None
    mem = it["memory"].replace(" ГБ", "")
    if "ТБ" in mem:
        mem = str(int(mem.replace(" ТБ", "")) * 1024)
    if mem not in info["mem"]:
        return None
    sim = "Есть" if cellular else "Нет"
    if sim not in info["sim"]:
        return None
    cs = (it.get("color_src") or "").lower()
    color = next((TAB_COLOR[k] for k in sorted(TAB_COLOR, key=len, reverse=True) if k in cs), None)
    if color not in info["colors"]:
        color = next((c for c in TAB_NEAR.get(color, []) if c in info["colors"]), None)
    if not color:
        return None
    return {"Brand": brand, "Model": model, "MemorySize": mem, "SimSlot": sim,
            "RamSize": info["mem"][mem], "Color": color}


def route(it):
    """Категория Авито и характеристики. None — категория ещё не настроена."""
    t = it["title"].lower()
    src = it["source_line"].lower()
    gt = it["goods_type"]
    base = {"Category": None}
    if gt == "Мобильные телефоны" and it.get("memory"):
        vendor, model = match_phone(it["model"])
        if (vendor, model) not in PHONES:
            model = re.sub(r"\s+[45]G$", "", model or "", flags=re.I)
        info = PHONES.get((vendor, model), {})
        mem = mem_for(it["memory"], info.get("mem"))
        nest = NESTED.get((vendor, model), {}).get(mem or "", {})
        color = color_for(it.get("color_src", ""), list(nest) or info.get("colors"))
        rams = nest.get(color or "")
        ram = it.get("ram")
        if not ram:  # в прайсе оперативки нет (Pixel) — берём из справочника для этой памяти и цвета
            ram = (rams or info.get("ram") or [None])[0]
        elif rams and ram not in rams:
            return None  # в справочнике Авито нет такой связки (память/цвет/оперативка) — не выкладываем
        p = {"Category": "Телефоны", "GoodsType": "Мобильные телефоны", "Vendor": vendor, "Model": model,
             "MemorySize": mem,
             "Color": color,
             "RamSize": ram,
             "SimConfig": it.get("sim") or None, "Set": "Коробка", "BoxSealed": "Да",
             "RegionalVersion": REGION.get(it.get("region", ""))}
        return p
    if "watch" in src or "garmin" in src or "whoop" in src:
        sub = "Фитнес-браслеты" if "whoop" in src else "Смарт-часы"
        return {"Category": "Телефоны", "GoodsType": "Смарт-часы и фитнес-браслеты", "GoodsSubType": sub}
    if "ring" in src and ("oura" in src or "galaxy ring" in t or "sm-q50" in src):
        return {"Category": "Телефоны", "GoodsType": "Смарт-часы и фитнес-браслеты", "GoodsSubType": "Умные кольца"}
    if gt == "Планшеты" and "keyboard" not in src:
        tp = tablet_params(it)
        if not tp:
            return None
        return {"Category": "Планшеты и электронные книги", "GoodsType": "Планшеты", "ProductsType": "Планшет",
                **tp, "BoxSealed": "Да"}
    if gt == "Ноутбуки":
        kb = "Есть кириллица" if re.search(r"\bru/a\b|кирил|рус", src) else "Нет кириллицы"
        return {"Category": "Ноутбуки", "KBLayout": kb}
    if re.search(r"airpods|buds|powerbeats", src):
        return {"Category": "Аудио и видео", "GoodsType": "Наушники"}
    if "magic keyboard" in src:
        return {"Category": "Товары для компьютера", "GoodsType": "Клавиатуры и мыши", "GoodsSubType": "Клавиатуры"}
    if "magic mouse" in src:
        return {"Category": "Товары для компьютера", "GoodsType": "Клавиатуры и мыши", "GoodsSubType": "Мыши"}
    if "playstation" in src and "drive" not in src:
        return {"Category": "Игры, приставки и программы", "GoodsType": "Игровые приставки и аксессуары",
                "ProductType": "Игровые приставки"}
    if "nintendo switch lite" in src or "switch oled" in src:
        return {"Category": "Игры, приставки и программы", "GoodsType": "Игровые приставки и аксессуары",
                "ProductType": "Игровые приставки"}
    if "dualsense" in src or "joy-con" in src:
        return {"Category": "Игры, приставки и программы", "GoodsType": "Игровые приставки и аксессуары",
                "ProductType": "Аксессуары", "ProductSubType": it.get("subtype") or "Геймпады и контроллеры",
                "Color": RU_CAP.get(color_for(it["source_line"], None) or "", "Другой")}
    if re.search(r"gopro|insta ?360|osmo 360|osmo pocket", src):
        return {"Category": "Аудио и видео", "GoodsType": "Видеокамеры", "ProductType": "Экшн-камеры"}
    if "ec35" in src:
        return {"Category": "Фототехника", "GoodsType": "Плёночные фотоаппараты"}
    if re.search(r"canon powershot|kodak|instax", src):
        return {"Category": "Фототехника", "GoodsType": "Компактные фотоаппараты"}
    if "яндекс станция" in src:
        return {"Category": "Аудио и видео", "GoodsType": "Акустика, колонки, сабвуферы", "GoodsSubType": "Умные колонки"}
    if "dyson hs08" in src:
        return {"Category": "Бытовая техника", "GoodsType": "Для индивидуального ухода",
                "ProductType": "Фены и приборы для укладки"}
    return None  # чехлы, адаптеры, очки, аксессуары камер — вторая очередь


def description(it):
    sim = f" SIM: {it['sim']}." if it.get("sim") else ""
    if it.get("region") in REGION_TEXT:
        sim += f" Версия: {REGION_TEXT[it['region']]}."
    return (f"<p><strong>{escape(it['title'])}</strong> — новый, оригинал, в заводской упаковке.{sim}</p>"
            "<ul><li>Гарантия 12 месяцев</li>"
            f"<li>Самовывоз: {ADDRESS}</li>"
            "<li>Цена актуальна на сегодня, обновляется ежедневно</li>"
            "<li>Пишите в чат — ответим и забронируем товар</li></ul>"
            "<p>Магазин ATOMM.STORE — техника Apple, Samsung, Google и другие бренды.</p>")


def ad_xml(it, prof, images, window=None):
    el = [("Id", it["id"])]
    if window:
        el += [("DateBegin", window[0]), ("DateEnd", window[1])]
    el += [("Address", ADDRESS), ("Title", it["title"]), ("Price", it["price"])]
    for k, v in prof.items():
        if v:
            el.append((k, v))
    el += [("AdType", "Товар приобретен на продажу"), ("Condition", "Новое"),
           ("CountryExpedition", COUNTRY), ("MultiItem", "Да"), ("ContactMethod", "По телефону и в сообщениях")]
    parts = [f"    <{k}>{escape(str(v))}</{k}>" for k, v in el]
    parts.append(f"    <Description><![CDATA[{sales_description(it, prof)}]]></Description>")
    parts.append("    <Delivery><Option>Выключена</Option></Delivery>")  # Авито Доставка выключена
    parts.append("    <Images>" + "".join(f'<Image url="{escape(u)}"/>' for u in images[:10]) + "</Images>")
    return "  <Ad>\n" + "\n".join(parts) + "\n  </Ad>"


def image_key(it):
    return f"{it.get('group') or it['title']}|{(it.get('color_src') or '').lower()}"


def build(items, images_map):
    ads, skipped, no_img = [], [], []
    window = show_window()
    for it in items:
        prof = route(it)
        if not prof:
            skipped.append(it["title"])
            continue
        imgs = images_map.get(image_key(it)) or images_map.get(it.get("group") or "", [])
        if not imgs:
            no_img.append(image_key(it))
            continue
        ads.append(ad_xml(it, prof, imgs, window))
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<Ads formatVersion="3" target="Avito.ru">\n' + "\n".join(ads) + "\n</Ads>\n"
    return xml, skipped, no_img


if __name__ == "__main__":
    items = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    imap_path = ROOT / "data" / "images.json"
    imap = json.loads(imap_path.read_text(encoding="utf-8")) if imap_path.exists() else {}
    xml, skipped, no_img = build(items, imap)
    Path(sys.argv[2]).write_text(xml, encoding="utf-8")
    print(f"ads: {xml.count('<Ad>')}  без категории: {len(skipped)}  без фото: {len(set(no_img))}")
