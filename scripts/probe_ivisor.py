"""Search ivisor HTML/JS for data endpoints."""
from __future__ import annotations

import re
import requests

HEADERS = {"User-Agent": "Mozilla/5.0"}
url = "https://saihweb.chsegura.es/apps/ivisor/index.php?variable=01A01Q02"
html = requests.get(url, headers=HEADERS, timeout=30).text
print("len", len(html))
for pat in (r'\.php[^"\']*', r'ajax[^"\']*', r'get[^"\']*\.php', r'variable[^"\']*'):
    found = set(re.findall(pat, html, re.I))
    for f in sorted(found)[:15]:
        print(pat, f[:80])
scripts = re.findall(r'src=["\']([^"\']+)["\']', html)
print("scripts", scripts)
