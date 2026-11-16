"""Проверка, какие разделы API Авито доступны с нашими ключами.
В репозиторий пишем только коды ответов и названия полей — без личных данных."""
import json, os, urllib.request, urllib.parse
from pathlib import Path

API = "https://api.avito.ru"


def call(method, path, token=None, body=None, form=None):
    data, headers = None, {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)[:100]}


def shape(x, depth=0):
    if isinstance(x, dict):
        return {k: shape(v, depth + 1) if depth < 1 else type(v).__name__ for k, v in list(x.items())[:15]}
    if isinstance(x, list):
        return f"list[{len(x)}]"
    return type(x).__name__


out = {}
st, tok = call("POST", "/token", form={"grant_type": "client_credentials",
                                        "client_id": os.environ.get("AVITO_CLIENT_ID", ""),
                                        "client_secret": os.environ.get("AVITO_CLIENT_SECRET", "")})
out["token"] = {"status": st, "ok": bool(tok.get("access_token")), "scope": tok.get("scope"),
                "error": tok.get("error")}
t = tok.get("access_token")
if t:
    st, me = call("GET", "/core/v1/accounts/self", t)
    uid = me.get("id")
    out["accounts/self"] = {"status": st, "fields": list(me)}
    checks = [
        ("GET", "/core/v1/items?per_page=1", None),
        ("GET", "/autoload/v2/profile", None),
        ("GET", "/autoload/v2/reports?per_page=1", None),
        ("GET", "/autoload/v2/reports/last_completed_report", None),
        ("GET", f"/messenger/v2/accounts/{uid}/chats?limit=1", None),
        ("GET", "/messenger/v3/webhook/subscriptions", None),
        ("POST", f"/stats/v1/accounts/{uid}/items", {"dateFrom": "2026-11-10", "dateTo": "2026-11-16",
                                                      "itemIds": [], "periodGrouping": "day"}),
        ("POST", "/cpa/v3/balanceInfo", {}),
        ("GET", "/tariff/info/1", None),
        ("GET", "/ratings/v1/info", None),
        ("GET", "/order-management/1/orders?limit=1", None),
        ("GET", f"/core/v1/accounts/{uid}/balance/", None),
        ("POST", "/cpxpromo/1/getBids/0", {}),
    ]
    for m, p, b in checks:
        st, r = call(m, p, t, body=b)
        key = p.replace(str(uid), "{id}").split("?")[0]
        out[key] = {"status": st, "shape": shape(r)}
Path("docs/api_probe.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps({k: v.get("status") for k, v in out.items()}))
