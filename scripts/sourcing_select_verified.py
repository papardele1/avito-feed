"""Select sourcing candidates only from independently verified Avito-market + Taobao data.

Does not scrape either website, buy products, or certify marking compliance.
Needs an authorized CSV export with the column schema in this module. Never
write private exports to the public repository.
"""
import argparse
import csv
import math
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

REQUIRED = [
    "sku", "name", "market_region", "market_source_url", "market_asof",
    "market_views_30d", "market_contacts_30d", "market_ads_30d", "avito_price_rub",
    "taobao_product_url", "taobao_shop", "seller_rating_5", "product_rating_5",
    "product_reviews", "sales_30d", "price_cny", "shipping_cny",
    "freight_rub", "import_and_docs_rub", "sale_cost_rub",
    "weight_g", "largest_side_cm", "tnved", "okpd2",
    "marking_required", "marking_checked_on", "marking_evidence_url",
]
OUTPUT = REQUIRED + ["landed_cost_rub", "profit_before_fixed_costs_rub", "margin_pct", "ranking_score", "result_reason"]

def number(row, key):
    return float(str(row.get(key, "")).strip().replace(",", "."))

def direct_taobao_url(raw):
    try:
        url = urlparse(raw)
        host = (url.hostname or "").lower()
        if url.scheme != "https":
            return False
        return host in ("item.taobao.com", "detail.tmall.com", "detail.tmall.hk", "m.tb.cn", "e.tb.cn")
    except ValueError:
        return False

def recent(raw, today, max_days=45):
    try:
        d = date.fromisoformat(raw)
        return 0 <= (today - d).days <= max_days
    except (TypeError, ValueError):
        return False

def validate(row, today, fx, max_weight, max_side):
    if not row.get("sku", "").strip() or not row.get("name", "").strip():
        return "missing SKU or product name"
    if row.get("market_region", "").strip().lower() not in ("москва", "moscow", "москва и московская область"):
        return "market data must cover Moscow"
    if not (row.get("market_source_url","").startswith("https://") and recent(row.get("market_asof"), today)):
        return "missing or stale (older than 45 days) market evidence"
    if not direct_taobao_url(row.get("taobao_product_url", "")):
        return "missing direct Taobao/Tmall product URL"
    if not row.get("taobao_shop", "").strip():
        return "missing shop name"
    if row.get("marking_required", "").strip().lower() not in ("no", "нет"):
        return "marking status unverified or required"
    if not (row.get("tnved", "").strip() and row.get("okpd2", "").strip()
            and row.get("marking_evidence_url", "").startswith("https://")
            and recent(row.get("marking_checked_on"), today, 120)):
        return "missing dated CHZ/TN VED/OKPD2 evidence"
    try:
        views, contacts, ads = (number(row, name) for name in ("market_views_30d", "market_contacts_30d", "market_ads_30d"))
        seller, item_rating, reviews = (number(row, name) for name in ("seller_rating_5", "product_rating_5", "product_reviews"))
        sales, price, ship = (number(row, name) for name in ("sales_30d", "price_cny", "shipping_cny"))
        freight, taxes, fee = (number(row, name) for name in ("freight_rub", "import_and_docs_rub", "sale_cost_rub"))
        avito, weight, side = (number(row, name) for name in ("avito_price_rub", "weight_g", "largest_side_cm"))
    except (ValueError, TypeError, OverflowError):
        return "missing or invalid numeric evidence"
    if min(views, contacts, ads, reviews, sales, price, ship, freight, taxes, fee) < 0:
        return "negative marketplace values"
    if contacts == 0 or sales == 0 or reviews < 20:
        return "insufficient demand or product reviews"
    if not (4.5 <= seller <= 5.0 and 4.6 <= item_rating <= 5.0):
        return "seller or item rating below threshold (5-point normalized scale)"
    if not (avito > 0 and 0 < weight <= max_weight and 0 < side <= max_side and price > 0):
        return "price, size or weight out of limits"
    landed = round((price + ship)*fx + freight + taxes, 2)
    profit = round(avito - fee - landed, 2)
    if profit <= 0:
        return "non-positive unit profit"
    margin = profit/avito
    if margin < 0.25:
        return "margin under 25%"
    demand = math.log1p(contacts) - 0.8*math.log1p(ads)
    quality = (seller+item_rating) + 0.2*math.log1p(reviews) + 0.1*math.log1p(sales)
    score = 3*demand + quality + 5*margin
    return {"landed_cost_rub":landed, "profit_before_fixed_costs_rub":profit,
            "margin_pct":round(100*margin,1), "ranking_score":round(score,3)}

def safe_for_csv(value):
    text = str(value) if value is not None else ""
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text

def select(source, approved_path, rejected_path, fx, max_weight=500, max_side=25, budget=1000000, limit=2000, today=None):
    if fx <= 0:
        raise ValueError("Currency exchange rate must be positive")
    today = today or date.today()
    with Path(source).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = sorted(set(REQUIRED).difference(reader.fieldnames or []))
        if missing:
            raise ValueError("Missing columns: " + ", ".join(missing))
        rows = list(reader)
    valid = []
    rejected = []
    for row in rows:
        result = validate(row, today, fx, max_weight, max_side)
        if isinstance(result, str):
            rejected.append({**row, "result_reason":result})
        else:
            valid.append({**row, **result, "result_reason":"candidate awaiting human approval"})
    valid.sort(key=lambda r: (r["ranking_score"], r["profit_before_fixed_costs_rub"]), reverse=True)
    approved, used_skus, spent = [], set(), 0
    for item in valid:
        if item["sku"] in used_skus:
            rejected.append({**item, "result_reason":"lower-ranked duplicate SKU"})
            continue
        if len(approved) >= limit or item["landed_cost_rub"] + spent > budget:
            rejected.append({**item, "result_reason":"budget or SKU limit"})
            continue
        approved.append(item)
        used_skus.add(item["sku"])
        spent += item["landed_cost_rub"]
    for path, data in ((approved_path, approved), (rejected_path, rejected)):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=OUTPUT, extrasaction="ignore")
            w.writeheader()
            w.writerows([{k:safe_for_csv(row.get(k,"")) for k in OUTPUT} for row in data])
    return {"approved_candidates":len(approved), "rejected":len(rejected), "budget_estimate":round(spent,2)}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("input_csv", type=Path)
    p.add_argument("--fx-rub-per-cny", type=float, required=True)
    p.add_argument("--approved", type=Path, default=Path("private_reports/approved_candidates.csv"))
    p.add_argument("--rejected", type=Path, default=Path("private_reports/rejected_candidates.csv"))
    p.add_argument("--max-weight", type=float, default=500)
    p.add_argument("--max-side", type=float, default=25)
    p.add_argument("--budget", type=float, default=1000000)
    p.add_argument("--limit", type=int, default=2000)
    args = p.parse_args()
    print(select(args.input_csv, args.approved, args.rejected, args.fx_rub_per_cny,
                 args.max_weight, args.max_side, args.budget, args.limit))

if __name__ == "__main__":
    main()
