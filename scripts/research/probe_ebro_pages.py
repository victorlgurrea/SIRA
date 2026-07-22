"""Probe saihebro.es WordPress pages for station data."""
from __future__ import annotations

import json
import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
RE = re.compile(r"let\s+(estaciones|aforos)\s*=\s*(\[.+?\]);", re.S)

for path in ("aforos", "estaciones", "datos", "mobile", "rsslatest.xml"):
    url = f"https://saihebro.es/{path}/"
    r = requests.get(url, headers=HEADERS, timeout=30)
    m = RE.search(r.text)
    print(path, r.status_code, len(r.text), "EMBED" if m else "")
    if m:
        data = json.loads(m.group(2))
        print(" n=", len(data), data[0] if data else "")
    # iframes / external apps
    for src in re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', r.text, re.I)[:5]:
        print("  iframe", src)
    for src in re.findall(r'src=["\']([^"\']+\.js[^"\']*)["\']', r.text):
        if "saih" in src.lower() or "estacion" in src.lower() or "mapa" in src.lower():
            print("  js", src)
