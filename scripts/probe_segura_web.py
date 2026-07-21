"""Probe Segura Web_Capas for live values."""
from __future__ import annotations

import json
import requests

HEADERS = {"User-Agent": "Mozilla/5.0"}
base = "https://chsegura.es/server/rest/services/VISOR_CHSIC3/VISOR_PUBLICO_ETRS89_v5_Web_Capas/MapServer"

r = requests.get(f"{base}?f=json", timeout=30)
meta = r.json()
for ly in meta.get("layers", [])[:25]:
    print(ly["id"], ly["name"])

for lid in (5, 8, 10, 11):
    url = f"{base}/{lid}/query"
    r = requests.get(url, params={
        "where": "1=1", "outFields": "*", "returnGeometry": "true",
        "f": "json", "resultRecordCount": "3",
    }, timeout=60)
    data = r.json()
    feats = data.get("features", [])
    print(f"\nWeb layer {lid}: n={len(feats)}")
    if feats:
        attrs = feats[0].get("attributes", {})
        print("keys", list(attrs.keys()))
        print(json.dumps(attrs, ensure_ascii=False)[:500])
