"""Мини-клиент API Авито (ключи — из секретов GitHub)."""
import json, os, urllib.request, urllib.parse, urllib.error

API = "https://api.avito.ru"
_token = None


def call(method, path, body=None, form=None, auth=True):
    global _token
    if auth and _token is None:
        st, r = call("POST", "/token", form={"grant_type": "client_credentials",
                                              "client_id": os.environ["AVITO_CLIENT_ID"],
                                              "client_secret": os.environ["AVITO_CLIENT_SECRET"]}, auth=False)
        _token = r["access_token"]
    data, headers = None, {}
    if auth:
        headers["Authorization"] = f"Bearer {_token}"
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}
