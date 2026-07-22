"""Probe SAIH Ebro/Segura endpoints."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from sira.infrastructure.http.client import fetch_json, fetch_text

def probe_ebro():
    print("=== EBRO ===")
    try:
        html = fetch_text("https://saihebro.es")
        print("home", len(html))
        for m in _RE_EMBED.finditer(html):
            print("embed var", m.group(1), "len", len(m.group(2)))
    except Exception as e:
        print("home err", e)
    for path in ("mapa-niveles", "mapa-aforos", "datos/", "wp-json/"):
        url = f"https://saihebro.es/{path}"
        try:
            html = fetch_text(url)
            m = _RE_EMBED.search(html)
            print(path, len(html), "EMBED" if m else "")
        except Exception as e:
            print(path, "ERR", e)


def probe_segura():
    print("=== SEGURA ===")
    url = "https://saihweb.chsegura.es/apps/iVisor/inicial.php"
    html = fetch_text(url)
    print("inicial", len(html))
    for m in _RE_EMBED.finditer(html):
        print("embed", m.group(1))
    # ArcGIS layers
    base = "https://chsegura.es/server/rest/services/VISOR_CHSIC3/VISOR_PUBLICO_ETRS89_v5_vectorial_dinamico/MapServer"
    try:
        meta = fetch_json(f"{base}?f=json")
        layers = meta.get("layers") or []
        print("layers", len(layers))
        for ly in layers[:20]:
            print(" ", ly.get("id"), ly.get("name"))
    except Exception as e:
        print("mapserver err", e)


_RE_EMBED = re.compile(r"let\s+(estaciones|aforos)\s*=\s*(\[.+?\]);", re.S)

if __name__ == "__main__":
    probe_ebro()
    probe_segura()
