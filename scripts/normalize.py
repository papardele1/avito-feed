"""Приведение текстов постов канала к строкам «Название - цена (хвост)».

Каждый пост канала — отдельный раздел прайса. Посты поставщик каждый день
редактирует, формат строк в них разный, поэтому здесь собраны правила для
каждого вида постов. Результат — текст с секциями «##Раздел», который
читает parse_price.py.
"""
import re

DISCLAIMER = re.compile(r"^Цена устройства фиксируется", re.I)
SKIP = re.compile(r"^(В наличии|Только ESIM|ESIM \+ физическая SIM|edited|\d+(\.\d+)?K$|\d{1,2}:\d{2}$)", re.I)
# «Название - 12345 (хвост)», допускаются тире — и –
PRICED_DASH = re.compile(r"^(?P<name>.+?)(?:\s[-–—]\s*|[-–—]\s+)(?P<price>\d{3,7})\b\s*\)?\s*(?P<tail>.*)$")
# «Название 12345» — цена через пробел
PRICED_SPACE = re.compile(r"^(?P<name>.+?)\s+(?P<price>\d{4,7})\s*(?P<tail>распак)?$")
# «Название 12345» (цена в конце без тире, в т.ч. приклеенная к /DS)
PRICED_END = re.compile(r"^(?P<name>.*?[A-Za-zА-Яа-я)/.\]+])\s*(?P<price>\d{4,7})\s*(?P<tail>распак)?$")

# Строки, где цена слиплась с цифрами названия — разбираем вручную
OVERRIDES = {
    "Ring SM-Q500 Titanium Gold 1017700": ("Samsung Galaxy Ring SM-Q500 Titanium Gold 10", 17700),
    "Kodak Charmera 19872800": ("Kodak Charmera 1987", 2800),
    "Kodak Charmera Millennium 20002900": ("Kodak Charmera Millennium 2000", 2900),
    "Kodak Charmera Millennium 2000 USA + Kodak MicroSD 16GB U1 V103800":
        ("Kodak Charmera Millennium 2000 USA + MicroSD 16GB", 3800),
    "Kodak Pixpro FZ5512000": ("Kodak Pixpro FZ55", 12000),
}

CYR_LAT = str.maketrans({"С": "C", "с": "c", "Р": "P", "р": "p", "О": "O", "о": "o",
                         "А": "A", "а": "a", "Е": "E", "е": "e", "М": "M", "Т": "T"})


def fix_latin(s):
    """Кириллические буквы-двойники внутри латинских слов (Сeramic, РOCO, Prо)."""
    def fix_word(w):
        lat = sum(c.isascii() and c.isalpha() for c in w)
        cyr = sum("а" <= c.lower() <= "я" or c in "ёЁ" for c in w)
        return w.translate(CYR_LAT) if lat and cyr and lat >= cyr else w
    return " ".join(fix_word(w) for w in s.split(" "))


def section_of(text):
    t = text[:400].lower()
    rules = [
        ("pitaka", "Чехлы PITAKA"), ("dualsense", "Консоли"), ("playstation", "Консоли"),
        ("apple watch", "Apple Watch"), ("airpods", "AirPods / Pencil / Keyboard / Mouse"),
        ("20w adapter", "Адаптеры и аксессуары"), ("macbook", "MacBook"), ("ipad", "iPad"), ("duo", "iPhone 18"),
        ("iphone 17", "iPhone 17"), ("iphone 16", "iPhone 16"), ("iphone 15", "iPhone 15/14"),
        ("dyson", "Dyson"), ("google", "Google"),
        ("honor", "Honor / POCO / Xiaomi / OnePlus"), ("samsung", "Samsung"),
        ("go pro", "Камеры"), ("ray ban", "Умные очки"), ("яндекс", "Яндекс Станции"),
        ("garmin", "Garmin"),
    ]
    for key, name in rules:
        if key in t:
            return name
    return None


def split_price(line):
    if line in OVERRIDES:
        n, p = OVERRIDES[line]
        return n, p, ""
    m = PRICED_DASH.match(line)
    if m:
        return m.group("name").strip(), int(m.group("price")), (m.group("tail") or "").strip()
    for rx in (PRICED_SPACE, PRICED_END):
        m = rx.match(line)
        if not m or (rx is PRICED_SPACE and 2015 <= int(m.group("price")) <= 2035):
            continue
        tail = "(распакован)" if m.group("tail") else ""
        return m.group("name").strip(), int(m.group("price")), tail
    return None


def is_sim_tail(tail):
    return bool(re.match(r"^\((e?sim|2\s?sim)", tail, re.I))


def normalize_post(text):
    section = section_of(text)
    if not section:
        return None, []
    lines = [fix_latin(re.sub(r"\s+", " ", l).strip()) for l in text.splitlines()]
    lines = [l for l in lines if l and not DISCLAIMER.match(l) and not SKIP.match(l)]
    out, header, pending = [], "", ""
    for line in lines:
        # «(без дисковода)» под ценой — уточнение к предыдущей позиции
        if line.startswith("(") and not re.search(r"\d{3,}", line) and out:
            n, p, t = out[-1]
            out[-1] = (f"{n} {line}", p, t)
            continue
        if line.startswith("(") and "шт" in line:  # оптовые цены
            continue
        sp = split_price(line)
        if not sp:
            if pending and re.match(r"[а-яё]", line):
                pending += " " + line
            else:
                header, pending = line, line
            continue
        name, price, tail = sp
        if pending and re.match(r"[а-яё]", name):
            name = pending + " " + name
        pending = ""
        if tail and not is_sim_tail(tail):
            name, tail = f"{name} {tail}", ""
        name = rule_name(section, header, name)
        if name:
            out.append((name, price, tail))
    return section, out


def rule_name(section, header, name):
    name = re.sub(r"\(\d{13}\)", "", name)          # EAN-коды очков
    name = re.sub(r"\s+", " ", name).strip()
    low = name.lower()
    if section == "Apple Watch":
        name = re.sub(r"^SE ", "SE3 ", name)
        return "Apple Watch " + name
    if section == "Dyson":
        return name if low.startswith("dyson") else "Dyson " + name
    if section == "Адаптеры и аксессуары":
        if header.lower().startswith("аксессуары iphone") and re.search(r"стекло|чехол|комплект", low):
            return f"{name} для iPhone 13/14/15/16/17"
        return name.replace("UCB-C", "USB-C").replace("(Ориг)", "(оригинал)").replace(" Ориг", " (оригинал)")
    if section == "Samsung":
        if low.startswith(("oura", "beats", "samsung")):
            return name
        name = re.sub(r"Z Fold Ultra 8", "Z Fold8 Ultra", name)
        name = re.sub(r"Z Fold 8", "Z Fold8", name)
        if low.startswith(("ring ", "buds", "galaxy buds", "watch")):
            return "Samsung Galaxy " + re.sub(r"^Galaxy ", "", name)
        return "Samsung " + name
    if section == "Google":
        return name if low.startswith("google") else "Google " + name
    if section == "Умные очки":
        if low.startswith(("oakley", "meta oakley")):
            return "Oakley Meta " + re.sub(r"^(Meta )?Oakley ", "", name)
        name = re.sub(r"^(Meta )?Ray[- ]?Ban (Meta )?", "", name)
        return "Ray-Ban Meta " + name
    if section == "Яндекс Станции":
        base = re.sub(r"\s*на YaGPT", "", header)
        return f"{base} {name}"
    if section == "Garmin":
        return name
    if section == "Чехлы PITAKA":
        dev = header
        if dev.lower().startswith("iphone"):
            return f"PITAKA Edge {dev} {name}"
        return f"PITAKA {dev} {name}"
    return name


def normalize_posts(posts):
    """posts: список текстов. Возвращает текст прайса с секциями и список пропусков."""
    blocks, seen, report = {}, set(), []
    for text in posts:
        section, items = normalize_post(text)
        if not section:
            continue
        for name, price, tail in items:
            key = (name.lower(), tail.lower())
            if key in seen:  # Magic Keyboard/Pencil/Mouse повторяются в нескольких постах
                continue
            seen.add(key)
            blocks.setdefault(section, []).append(f"{name} - {price}" + (f" {tail}" if tail else ""))
    text = "\n".join(f"##{s}\n" + "\n".join(lines) for s, lines in blocks.items())
    return text, report
