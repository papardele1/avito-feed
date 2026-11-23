import csv
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from sourcing_select_verified import REQUIRED, select, validate

TODAY = date(2026, 11, 23)

def example():
    return {
        "sku":"C0001", "name":"Test cable clip",
        "market_region":"Москва", "market_source_url":"https://example.com/avito-market-evidence",
        "market_asof":"2026-11-22", "market_views_30d":"2000",
        "market_contacts_30d":"150", "market_ads_30d":"30", "avito_price_rub":"600",
        "taobao_product_url":"https://item.taobao.com/item.htm?id=12345",
        "taobao_shop":"Test verified shop", "seller_rating_5":"4.9",
        "product_rating_5":"4.9", "product_reviews":"400", "sales_30d":"150",
        "price_cny":"10", "shipping_cny":"2", "freight_rub":"30",
        "import_and_docs_rub":"20", "sale_cost_rub":"30",
        "weight_g":"60", "largest_side_cm":"8", "tnved":"3926909709",
        "okpd2":"22.29.29", "marking_required":"no",
        "marking_checked_on":"2026-11-22",
        "marking_evidence_url":"https://markirovka.ru/knowledge/"
    }

class SelectionTests(unittest.TestCase):
    def test_valid_row_has_positive_margin(self):
        result = validate(example(), TODAY, 11.0, 500, 25)
        self.assertIsInstance(result, dict)
        self.assertGreater(result["profit_before_fixed_costs_rub"], 0)

    def test_unchecked_marking_is_rejected(self):
        r = example(); r["marking_required"] = "unknown"
        self.assertIn("marking", validate(r, TODAY, 11.0, 500, 25))

    def test_old_market_stats_rejected(self):
        r = example(); r["market_asof"] = "2026-01-01"
        self.assertIn("stale", validate(r, TODAY, 11.0, 500, 25))

    def test_fake_taobao_domain_rejected(self):
        r = example(); r["taobao_product_url"] = "https://item.taobao.com.evil.test/item.htm"
        self.assertIn("product URL", validate(r, TODAY, 11.0, 500, 25))

    def test_duplicate_sku_and_bad_rows(self):
        row = example(); other = example(); other["taobao_product_url"] = "http://wrong.test/"
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); inp = root/"input.csv"
            with inp.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=REQUIRED)
                writer.writeheader()
                writer.writerows([row, example(), other])
            result = select(inp, root/"approved.csv", root/"rejected.csv", 11.0, today=TODAY)
            self.assertEqual(result["approved_candidates"], 1)
            self.assertEqual(result["rejected"], 2)

if __name__ == "__main__":
    unittest.main()
