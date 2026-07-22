import requests, re
HEADERS = {"User-Agent": "Mozilla/5.0"}
for path in ("mobile/", "estaciones/", "aforos/"):
    html = requests.get(f"https://saihebro.es/{path}", headers=HEADERS, timeout=30).text
    for u in re.findall(r'https?://[^"\'\s<>]+', html):
        if any(k in u.lower() for k in ("api", "saih", "chebro", "miteco", "json", "cedex")):
            print(path, u[:120])
