import json, sys
sys.path.insert(0, "scripts")
from avito_api import call
st, r = call("GET", "/autoload/v2/reports?per_page=3")
print("reports", json.dumps(r.get("reports"), ensure_ascii=False))
rid = r["reports"][0]["id"]
st, rep = call("GET", f"/autoload/v3/reports/{rid}")
rep.pop("_deprecation", None)
print("report", json.dumps(rep, ensure_ascii=False)[:3000])
st, it = call("GET", f"/autoload/v2/reports/{rid}/items?per_page=2")
print("items", json.dumps(it.get("items"), ensure_ascii=False)[:2000], it.get("meta"))
st, ci = call("GET", "/core/v1/items?per_page=2&status=active,old,blocked,rejected")
print("core items", st, json.dumps(ci, ensure_ascii=False)[:1000])
