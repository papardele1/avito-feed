"""Rank documented Avito-market candidates for Taobao supplier verification.

Input must be from a permitted market-demand data export; OWN listing API
statistics are NOT a substitute for market demand. Search links are NOT
verified seller/product URLs. Unknown marking status is always rejected.
"""
import argparse
import csv
import math
from pathlib import Path
from urllib.parse import quote_plus

REQUIRED = (
    "name_ru", "search_zh", "views_30d", "contacts_30d", "competing_ads",
    "weight_g", "max_dimension_cm", "chz_checked", "chz_required", "source_url",
)

def number(value):
    try:
        return float(str(value).strip().replace(",", "."))
    except (ValueError, TypeError):
        return -1

def qualified(row, max_weight_g, max_dimension_cm):
    if row["chz_checked"].strip().lower() not in ("yes", "да", "true", "1"):
        return False
    if row["chz_required"].strip().lower() not in ("no", "нет", "false", "0"):
        return False
    if not row["source_url"].strip() or not row["name_ru"].strip():
        return False
    weight = number(row["weight_g"])
    size = number(row["max_dimension_cm"])
    return 0 < weight <= max_weight_g and 0 < size <= max_dimension_cm

def run(source, target, limit, max_weight_g, max_dimension_cm):
    with source.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = sorted(set(REQUIRED) - set(reader.fieldnames or ()))
        if missing:
            raise ValueError("Missing CSV columns: " + ", ".join(missing))
        rows = list(reader)
    ranked = []
    for row in rows:
        if not qualified(row, max_weight_g, max_dimension_cm):
            continue
        views = number(row["views_30d"])
        contacts = number(row["contacts_30d"])
        ads = number(row["competing_ads"])
        if min(views, contacts, ads) < 0:
            continue
        score = 4.0 * math.log1p(contacts) + 1.4 * math.log1p(views) - 1.2 * math.log1p(ads)
        q = row["search_zh"].strip()
        ranked.append({
            "name_ru": row["name_ru"].strip(),
            "avito_views_30d": int(views),
            "avito_contacts_30d": int(contacts),
            "avito_competing_ads": int(ads),
            "weight_g": number(row["weight_g"]),
            "max_dimension_cm": number(row["max_dimension_cm"]),
            "demand_score": round(score, 3),
            "market_source_url": row["source_url"].strip(),
            "taobao_search_url": ("https://s.taobao.com/search?q=" + quote_plus(q)) if q else "",
            "taobao_product_url": "",
            "seller_rating": "",
            "product_rating": "",
            "verification_status": "NEEDS_TAOBAO_PRODUCT_AND_RATING_CHECK",
            "chz_checked": "yes",
            "chz_required": "no",
        })
    ranked.sort(key=lambda r: r["demand_score"], reverse=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "name_ru", "avito_views_30d", "avito_contacts_30d", "avito_competing_ads",
        "weight_g", "max_dimension_cm", "demand_score", "market_source_url",
        "taobao_search_url", "taobao_product_url", "seller_rating", "product_rating",
        "verification_status", "chz_checked", "chz_required",
    ]
    with target.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(ranked[:limit])
    print(f"Qualified candidates: {len(ranked)}; saved: {min(limit, len(ranked))}")
    print("Supplier product URLs and ratings remain unverified; no purchase approval.")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("input_csv", type=Path)
    p.add_argument("--out", type=Path, default=Path("private_reports/shortlist.csv"))
    p.add_argument("--limit", type=int, default=2000)
    p.add_argument("--max-weight-g", type=float, default=500)
    p.add_argument("--max-dimension-cm", type=float, default=25)
    args = p.parse_args()
    run(args.input_csv, args.out, args.limit, args.max_weight_g, args.max_dimension_cm)
