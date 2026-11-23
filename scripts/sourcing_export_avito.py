"""Export statistics for OWN Avito ads; does not measure marketplace demand.

Uses existing AVITO_CLIENT_ID and AVITO_CLIENT_SECRET via scripts/avito_api.py.
Never commit the generated CSV to this public repository.
"""
import argparse
import csv
import json
from datetime import date, timedelta
from pathlib import Path
from avito_api import call

METRICS = ("uniqViews", "uniqContacts", "uniqFavorites")

def request(method, path, body=None):
    status, data = call(method, path, body)
    if status != 200:
        raise RuntimeError(f"Avito API HTTP {status} at {path.split('?')[0]}")
    return data

def listings():
    all_rows = []
    for page in range(1, 51):
        resp = request("GET", f"/core/v1/items?per_page=100&page={page}&status=active")
        part = resp.get("resources") or []
        all_rows.extend(x for x in part if isinstance(x, dict) and x.get("id") is not None)
        if len(part) < 100:
            return all_rows
    raise RuntimeError("Reached 50-page limit: export may be incomplete")

def export(days, path):
    me = request("GET", "/core/v1/accounts/self")
    uid = int(me["id"])
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    items = listings()
    details = {int(x["id"]): x for x in items}
    totals = {item_id: {metric: 0 for metric in METRICS} for item_id in details}
    ids = list(details)
    for offset in range(0, len(ids), 200):
        response = request("POST", f"/stats/v1/accounts/{uid}/items", {
            "dateFrom": start.isoformat(),
            "dateTo": end.isoformat(),
            "itemIds": ids[offset:offset + 200],
            "fields": list(METRICS),
            "periodGrouping": "day",
        })
        for item in (response.get("result") or {}).get("items", []):
            item_id = int(item["itemId"])
            if item_id not in totals:
                continue
            for daily in item.get("stats") or []:
                for metric in METRICS:
                    totals[item_id][metric] += int(daily.get(metric) or 0)
    rows = []
    for item_id, obj in details.items():
        category = obj.get("category") or {}
        price = obj.get("price")
        if isinstance(price, dict):
            price = price.get("value")
        rows.append({
            "item_id": item_id,
            "title": obj.get("title") or "",
            "category": category.get("name", "") if isinstance(category, dict) else str(category),
            "price_rub": price if isinstance(price, (int, float)) else "",
            "views": totals[item_id]["uniqViews"],
            "contacts": totals[item_id]["uniqContacts"],
            "favorites": totals[item_id]["uniqFavorites"],
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "source": "own_avito_listings_api",
        })
    rows.sort(key=lambda row: (row["contacts"], row["views"], row["favorites"]), reverse=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["item_id", "title", "category", "price_rub", "views", "contacts", "favorites", "start_date", "end_date", "source"]
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"rows": len(rows), "source": "own_avito_listings_api", "period": [start.isoformat(), end.isoformat()]}, ensure_ascii=False))

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--out", type=Path, default=Path("private_reports/avito_own_stats.csv"))
    args = p.parse_args()
    if not (1 <= args.days <= 365):
        p.error("--days must be 1 to 365")
    export(args.days, args.out)
