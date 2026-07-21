"""Analyze Ebro HTML and Segura ArcGIS layers."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def ebro():
    r = requests.get("https://saihebro.es/mapa-niveles", headers=HEADERS, timeout=30)
    html = r.text
    print("EBRO HTML snippet:")
    print(html[2000:4000])
    scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, re.I)
    print("scripts", scripts)
    for s in scripts:
        if s.startswith("/"):
            s = "https://saihebro.es" + s
        if "saihebro" in s:
            try:
                js = requests.get(s, headers=HEADERS, timeout=30).text
                if "estaciones" in js or "aforos" in js:
                    print("JS", s, len(js), "has estaciones")
                    for m in re.finditer(r'https?://[^"\']+', js):
                        u = m.group(0)
                        if any(k in u for k in ("api", "json", "dato", "estacion")):
                            print("  url", u[:120])
            except Exception as e:
                print("JS err", s, e)


def segura():
    base = "https://chsegura.es/server/rest/services/VISOR_CHSIC3/VISOR_PUBLICO_ETRS89_v5_vectorial_dinamico/MapServer"
    r = requests.get(f"{base}?f=json", timeout=30)
    meta = r.json()
    for ly in meta.get("layers", []):
        print(ly["id"], ly["name"])

    for lid in (10, 11):
        url = f"{base}/{lid}/query"
        r = requests.get(url, params={
            "where": "1=1", "outFields": "*", "returnGeometry": "true",
            "f": "json", "resultRecordCount": "2",
        }, timeout=60)
        data = r.json()
        feats = data.get("features", [])
        print(f"\nLayer {lid}: {len(feats)} sample, total?", data.get("exceededTransferLimit"))
        if feats:
            print("attrs", feats[0].get("attributes"))
            print("geom", feats[0].get("geometry"))


if __name__ == "__main__":
    ebro()
    segura()
