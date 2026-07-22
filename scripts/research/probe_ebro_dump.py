"""Dump saihebro mapa-niveles content patterns."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from sira.infrastructure.http.client import fetch_text

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}
html = fetch_text("https://saihebro.es/mapa-niveles", headers=UA)
print("len", len(html))
print(html[:1500])
print("---")
for pat in [r'let\s+\w+\s*=\s*\[', r'var\s+\w+\s*=\s*\[', r'fetch\([^)]+\)', r'\.json', r'estacion', r'aforo']:
    ms = re.findall(pat, html, re.I)
    print(pat, len(ms), ms[:5])
