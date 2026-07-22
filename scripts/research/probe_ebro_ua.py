"""Probe Ebro SAIH with browser headers."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from sira.infrastructure.http.client import fetch_text

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
}

RE = re.compile(r"let\s+(estaciones|aforos)\s*=\s*(\[.+?\]);", re.S)

for base in ("https://saihebro.es", "https://www.saihebro.com"):
    for path in ("mapa-niveles", "mapa-aforos"):
        url = f"{base}/{path}"
        try:
            html = fetch_text(url, headers=UA)
            m = RE.search(html)
            print(url, "OK", len(html), "EMBED" if m else "")
            if m:
                print("  var", m.group(1), "chars", len(m.group(2)))
        except Exception as e:
            print(url, "ERR", e)
