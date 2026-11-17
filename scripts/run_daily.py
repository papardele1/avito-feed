"""Ежедневный прогон: Telegram → разбор → цены +3,5% → фид Авито в docs/avito.xml."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_feed  # noqa: E402
import normalize  # noqa: E402
import parse_price  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FEED = ROOT / "docs" / "avito.xml"
MIN_SHARE = 0.6  # если позиций меньше 60% от прошлого раза — фид не трогаем


def main():
    from telegram_fetch import get_posts
    posts = get_posts()
    priced = [p for p in posts if len(re.findall(r"\d{4,6}", p)) >= 3]
    text, _ = normalize.normalize_posts(priced)
    items, errors = parse_price.run(text=text)
    for it in items:
        it["title"] = parse_price.short_title(it["title"])
    # ручные правки позиций (название, фото, регион, подтип, характеристики) — data/overrides.json
    ov_path = ROOT / "data" / "overrides.json"
    overrides = json.loads(ov_path.read_text(encoding="utf-8")) if ov_path.exists() else []
    for it in items:
        for o in overrides:
            if o["match"].lower() in (it["source_line"] + " " + it["title"]).lower():
                it["title"] = o.get("title", it["title"])
                it["group"] = it["title"]
                for k in ("region", "subtype", "image"):
                    if o.get(k):
                        it[k] = o[k]
                it["extra_specs"] = o.get("specs", [])
    # фото, найденные вручную на других сайтах (docs/img/cand) — data/photo_queries.json:
    # [имя файла, слова, которые все должны быть в строке, слова-исключения]
    pq_path = ROOT / "data" / "photo_queries.json"
    cand_dir = ROOT / "docs" / "img" / "cand"
    rules = []
    for q in (json.loads(pq_path.read_text(encoding="utf-8")) if pq_path.exists() else []):
        if (cand_dir / (q[0] + ".jpg")).exists():
            rules.append((q[0], [w.lower() for w in q[1]], [w.lower() for w in q[2]]))
    rules.sort(key=lambda r: -sum(len(w) for w in r[1]))  # самые точные правила первыми
    for it in items:
        if it.get("image"):
            continue
        text = " " + (it["source_line"] + " " + it["title"]).lower() + " "
        for slug, need, excl in rules:
            if all(w in text for w in need) and not any(w in text for w in excl):
                it["image"] = f"cand/{slug}.jpg"
                break
    # Apple Watch, отличающиеся только размером ремешка (S/M и M/L, M и L), — одно объявление:
    # Авито считает их одним товаром и блокирует второе как «повторное размещение».
    # Цена — бо́льшая из пары, оба размера указываем в описании. Id берём у объявления,
    # которое на Авито активно (заблокированные перечислены ниже).
    aw_blocked = {"Apple Watch SE3 44 Midnight 2026 M/L", "Apple Watch S11 46 Space Gray S/M",
                  "Apple Watch S12 46 Space Gray S/M", "Apple Watch SE3 40 Midnight 2026 S/M",
                  "Apple Watch S11 46 Silver Pur Fog S/M", "Watch Ultra 4 49 Natural Desert Alpine Loop M",
                  "Apple Watch S11 42 Jet Black S/M", "Apple Watch S12 46 Bronze Milanese Loop S/M"}
    band_re = re.compile(r"\s+(S/M|M/L|S|M|L)\s*$")
    groups = {}
    for it in items:
        t = it["title"]
        if "Watch" in t and band_re.search(t) and not re.search(r"Galaxy|Pixel|OnePlus|Huawei|Xiaomi", t):
            groups.setdefault(band_re.sub("", t), []).append(it)
    drop = set()
    for base, its in groups.items():
        if len(its) < 2:
            continue
        sizes = [band_re.search(i["title"]).group(1) for i in its]
        keep = next((i for i in its if i["title"] not in aw_blocked), its[0])
        keep["price"] = max(i["price"] for i in its)
        keep["title"] = keep["group"] = base
        keep["extra_specs"] = (keep.get("extra_specs") or []) + [
            ["Размер ремешка", " и ".join(sorted(sizes, key=len, reverse=True)) + " — оба в наличии, укажите нужный при заказе"]]
        drop.update(id(i) for i in its if i is not keep)
    items = [it for it in items if id(it) not in drop]
    # позиции вне прайса (от других поставщиков) с фиксированной ценой — data/manual_items.json
    man_path = ROOT / "data" / "manual_items.json"
    for m in (json.loads(man_path.read_text(encoding="utf-8")) if man_path.exists() else []):
        m = dict(m, group=m["title"], manual=True)
        items.append(m)
    import images
    try:
        imap, img_ok, img_missed = images.ensure_images(items, build_feed.route)
    except Exception as e:  # noqa: BLE001 — без фото с сайта используем прошлую карту
        print("Фото с atomm.store не получены:", e)
        imap_path = ROOT / "data" / "images.json"
        imap = json.loads(imap_path.read_text(encoding="utf-8")) if imap_path.exists() else {}
        img_ok, img_missed = [], []
    else:
        (ROOT / "data" / "images.json").write_text(json.dumps(imap, ensure_ascii=False, indent=1), encoding="utf-8")
    for it in items:
        if it.get("image"):
            imap[build_feed.image_key(it)] = [images.RAW_BASE + it["image"]]
    xml, skipped, no_img = build_feed.build(items, imap)
    new_ads = xml.count("<Ad>")
    old_ads = FEED.read_text(encoding="utf-8").count("<Ad>") if FEED.exists() else 0
    print(f"позиций в прайсе: {len(items)}, нераспознанных строк: {len(errors)}, "
          f"объявлений: {new_ads} (было {old_ads}), без категории: {len(skipped)}, без фото: {len(set(no_img))}")
    for e in errors[:30]:
        print("  НЕ РАЗОБРАНО:", e)
    if old_ads and new_ads < old_ads * MIN_SHARE:
        raise SystemExit(f"Объявлений стало подозрительно мало ({new_ads} из {old_ads}) — фид не обновлён.")
    FEED.parent.mkdir(exist_ok=True)
    FEED.write_text(xml, encoding="utf-8")
    report = {"items": len(items), "ads": new_ads, "skipped": skipped, "no_images": sorted(set(no_img)),
              "unparsed": errors,
              "photos_matched": img_ok, "photos_missed": img_missed,
              "all": [f"{i['title']} | {i['price']} | {i.get('region','')} | {i['source_line']}" for i in items]}
    (ROOT / "docs" / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
