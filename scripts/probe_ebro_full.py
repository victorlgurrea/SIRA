import re, requests, json
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
html = requests.get("https://saihebro.es/mapa-niveles", headers=HEADERS, timeout=30).text
print(html)
# search json blobs
for m in re.finditer(r'\{[^{}]{50,500}\}', html):
    s = m.group(0)
    if any(k in s.lower() for k in ('api', 'url', 'estacion', 'config')):
        print("json?", s[:200])
