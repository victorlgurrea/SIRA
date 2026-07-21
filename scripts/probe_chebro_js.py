"""Extract API URLs from saih.chebro.es homepage."""
from __future__ import annotations

import re
import requests

HEADERS = {"User-Agent": "Mozilla/5.0"}
r = requests.get("https://saih.chebro.es/", headers=HEADERS, timeout=30)
html = r.text
print("len", len(html))
urls = set(re.findall(r'https?://[^"\'\\s<>]+', html))
for u in sorted(urls):
    if any(k in u.lower() for k in ("api", "estacion", "mapa", "saih", "nivel", "aforo", "json")):
        print(u)
# script bundles
for s in re.findall(r'src=["\']([^"\']+\.js[^"\']*)["\']', html):
    if not s.startswith("http"):
        s = "https://saih.chebro.es" + s
    try:
        js = requests.get(s, headers=HEADERS, timeout=30).text
        if "estaciones" in js and "mapa" in js:
            print("JS candidate", s, len(js))
            for m in re.finditer(r'["\'](/[^"\']*(?:api|estacion|mapa)[^"\']*)["\']', js):
                print("  path", m.group(1)[:100])
    except Exception:
        pass
