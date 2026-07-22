"""Search saihebro.es HTML for data endpoints."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from sira.infrastructure.http.client import fetch_text

html = fetch_text("https://saihebro.es")
# URLs in page
urls = set(re.findall(r'["\']([^"\']*(?:mapa|estacion|saih|api|json|dato)[^"\']*)["\']', html, re.I))
for u in sorted(urls)[:50]:
    print(u)
print("---")
# inline data patterns
for pat in [r'api[^"\']+', r'/wp-content/[^"\']+', r'saih[^"\']+']:
    found = set(re.findall(pat, html, re.I))
    for f in sorted(found)[:20]:
        print("pat", f[:100])
