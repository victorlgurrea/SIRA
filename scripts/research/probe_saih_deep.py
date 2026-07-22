"""Deep probe SAIH Ebro and Segura."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from sira.config.settings import ALLOWED_HOSTS

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
}

RE_EMBED = re.compile(r"let\s+(estaciones|aforos)\s*=\s*(\[.+?\]);", re.S)


def get(url: str) -> requests.Response:
    host = url.split("/")[2]
    if host not in ALLOWED_HOSTS:
        raise ValueError(f"not allowed: {host}")
    return requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)


def probe_ebro():
    print("=== EBRO ===")
    for path in ("mapa-niveles", "mapa-aforos"):
        url = f"https://saihebro.es/{path}"
        r = get(url)
        print(path, r.status_code, len(r.text), r.headers.get("content-type", "")[:40])
        m = RE_EMBED.search(r.text)
        if m:
            data = json.loads(m.group(2))
            print("  embed", m.group(1), "n=", len(data))
            if data:
                print("  keys", list(data[0].keys())[:12])
        else:
            # search other patterns
            for pat in (r"estaciones\s*[:=]", r"application/json", r"api/"):
                if re.search(pat, r.text, re.I):
                    print("  found", pat)


def probe_segura():
    print("=== SEGURA ===")
    # iVisor PHP endpoints
    bases = [
        "https://saihweb.chsegura.es/apps/iVisor/",
        "https://saihweb.chsegura.es/apps/iVisor/datos/",
    ]
    for base in bases:
        for name in ("getEstaciones.php", "estaciones.php", "mapaDatos.php", "datosTiempoReal.php", "ajax_estaciones.php"):
            url = base + name
            try:
                r = get(url)
                print(name, r.status_code, len(r.text), r.text[:120].replace("\n", " "))
            except Exception as e:
                print(name, "skip", e)

    # ArcGIS with requests directly
    url = "https://chsegura.es/server/rest/services/VISOR_CHSIC3/VISOR_PUBLICO_ETRS89_v5_vectorial_dinamico/MapServer/10/query"
    r = requests.get(url, params={"where": "1=1", "outFields": "*", "returnGeometry": "true", "f": "json", "resultRecordCount": "3"}, headers=HEADERS, timeout=30)
    print("arcgis", r.status_code, r.text[:200])


if __name__ == "__main__":
    probe_ebro()
    probe_segura()
