import re, sys, urllib.request, json
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36", "Accept-Language": "ru-RU,ru;q=0.9"}
url = sys.argv[1]
page = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read().decode("utf-8", "ignore")
print("len", len(page))
for m in list(re.finditer(r"get-mpic", page))[:4]:
    print("CTX", page[max(0, m.start()-600):m.start()+200].replace("\n", " "))
    print("-----")
