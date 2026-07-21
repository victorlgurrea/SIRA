import requests, re
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "text/html,*/*"}
RE = re.compile(r"let\s+estaciones\s*=\s*(\[.+?\]);", re.S)
hosts = [
    "https://saihduero.es/mapa-niveles",
    "https://www.saihduero.es/mapa-niveles",
    "https://saih.chduero.es/mapa-niveles",
    "http://saihebro.com/semobile/",
    "https://datos.chebro.es/saih/mapa-niveles",
]
for url in hosts:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        m = RE.search(r.text)
        print(url, r.status_code, len(r.text), "EMBED" if m else "")
    except Exception as e:
        print(url, type(e).__name__)
