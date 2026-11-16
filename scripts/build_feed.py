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
COUNTRY = "Китай"

EN_RU = {
    "black": "черный", "jet black": "черный", "jetblack": "черный", "midnight": "черный", "night sky": "черный",
    "space black": "черный", "obsidian": "черный", "infinite black": "черный", "black velvet": "черный",
    "white": "белый", "star white": "белый", "starlight": "белый", "snow": "белый", "frost": "белый",
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
    "olive": "зеленый", "starlit green": "зеленый", "aurora green": "зеленый", "green shadow": "зеленый",
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
    near = {"голубой": "синий", "синий": "голубой", "серый": "черный", "серебристый": "белый",
            "золотистый": "бежевый", "бежевый": "золотистый"}.get(cand)
    return near if near in allowed else None


def mem_for(mem_ru, allowed):
    v = mem_ru.replace(" ТБ", "TB").replace(" ГБ", "")
    if v.endswith("TB"):
        v = str(int(v[:-2]) * 1024)
    val = f"{v} ГБ"
    return val if (not allowed or val in allowed) else None


def route(it):
    """Категория Авито и характеристики. None — категория ещё не настроена."""
    t = it["title"].lower()
    src = it["source_line"].lower()
    gt = it["goods_type"]
    base = {"Category": None}
    if gt == "Мобильные телефоны" and it.get("memory"):
        vendor, model = match_phone(it["model"])
        info = PHONES.get((vendor, model), {})
        p = {"Category": "Телефоны", "GoodsType": "Мобильные телефоны", "Vendor": vendor, "Model": model,
             "MemorySize": mem_for(it["memory"], info.get("mem")),
             "Color": color_for(it.get("color_src", ""), info.get("colors")),
             "RamSize": it.get("ram") or (info.get("ram") or [None])[0],
             "SimConfig": it.get("sim") or None, "Set": "Коробка", "BoxSealed": "Да",
             "RegionalVersion": REGION.get(it.get("region", ""))}
        return p
    if "watch" in src or "garmin" in src or "whoop" in src:
        sub = "Фитнес-браслеты" if "whoop" in src else "Смарт-часы"
        return {"Category": "Телефоны", "GoodsType": "Смарт-часы и фитнес-браслеты", "GoodsSubType": sub}
    if "ring" in src and ("oura" in src or "galaxy ring" in t or "sm-q50" in src):
        return {"Category": "Телефоны", "GoodsType": "Смарт-часы и фитнес-браслеты", "GoodsSubType": "Умные кольца"}
    if gt == "Планшеты" and "keyboard" not in src:
        return {"Category": "Планшеты и электронные книги", "GoodsType": "Планшеты"}
    if gt == "Ноутбуки":
        return {"Category": "Ноутбуки"}
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
                "ProductType": "Аксессуары", "ProductSubType": "Геймпады и контроллеры",
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


def ad_xml(it, prof, images):
    el = [("Id", it["id"]), ("Address", ADDRESS), ("Title", it["title"]), ("Price", it["price"])]
    for k, v in prof.items():
        if v:
            el.append((k, v))
    el += [("AdType", "Товар приобретен на продажу"), ("Condition", "Новое"),
           ("CountryExpedition", COUNTRY), ("MultiItem", "Да"), ("ContactMethod", "По телефону и в сообщениях")]
    parts = [f"    <{k}>{escape(str(v))}</{k}>" for k, v in el]
    parts.append(f"    <Description><![CDATA[{sales_description(it, prof)}]]></Description>")
    parts.append("    <Images>" + "".join(f'<Image url="{escape(u)}"/>' for u in images[:10]) + "</Images>")
    return "  <Ad>\n" + "\n".join(parts) + "\n  </Ad>"


def image_key(it):
    return f"{it.get('group') or it['title']}|{(it.get('color_src') or '').lower()}"


def build(items, images_map):
    ads, skipped, no_img = [], [], []
    for it in items:
        prof = route(it)
        if not prof:
            skipped.append(it["title"])
            continue
        imgs = images_map.get(image_key(it)) or images_map.get(it.get("group") or "", [])
        if not imgs:
            no_img.append(image_key(it))
            continue
        ads.append(ad_xml(it, prof, imgs))
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<Ads formatVersion="3" target="Avito.ru">\n' + "\n".join(ads) + "\n</Ads>\n"
    return xml, skipped, no_img


if __name__ == "__main__":
    items = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    imap_path = ROOT / "data" / "images.json"
    imap = json.loads(imap_path.read_text(encoding="utf-8")) if imap_path.exists() else {}
    xml, skipped, no_img = build(items, imap)
    Path(sys.argv[2]).write_text(xml, encoding="utf-8")
    print(f"ads: {xml.count('<Ad>')}  без категории: {len(skipped)}  без фото: {len(set(no_img))}")
