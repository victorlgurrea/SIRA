"""Probe saih.chebro.es for CHJ-style embed."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
RE = re.compile(r"let\s+(estaciones|aforos)\s*=\s*(\[.+?\]);", re.S)

for host in ("saih.chebro.es", "datos.chebro.es"):
    for path in ("mapa-niveles", "mapa-aforos", "MapaNiveles", "mapas/mapa-niveles"):
        url = f"https://{host}/{path}"
        r = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
        m = RE.search(r.text)
        print(url, r.status_code, len(r.text), "EMBED" if m else "")
        if m:
            data = json.loads(m.group(2))
            print(" ", m.group(1), len(data), list(data[0].keys())[:10] if data else "")
