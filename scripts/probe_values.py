"""Find live values in Segura SAIH and Ebro API."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/html,*/*"}


def segura_ivisor():
    var = "01A01Q02"
    urls = [
        f"https://saihweb.chsegura.es/apps/ivisor/index.php?variable={var}",
        f"https://saihweb.chsegura.es/apps/iVisor/datos.php?variable={var}",
        f"https://saihweb.chsegura.es/apps/iVisor/getValor.php?variable={var}",
        f"https://saihweb.chsegura.es/apps/iVisor/ultimoValor.php?codigo={var}",
    ]
    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            print(url, r.status_code, r.text[:200].replace("\n", " "))
        except Exception as e:
            print(url, e)

    # dynamic map service
    bases = [
        "https://chsegura.es/server/rest/services/VISOR_CHSIC3/VISOR_PUBLICO_ETRS89_v5_Web_Capas/MapServer",
        "https://chsegura.es/server/rest/services/VISOR_CHSIC3/VISOR_PUBLICO_ETRS89_v5_vectorial_dinamico/MapServer/8",
    ]
    for base in bases:
        r = requests.get(f"{base}?f=json", headers=HEADERS, timeout=30)
        if r.ok:
            d = r.json()
            print("service", base.split("/")[-1], "layers", len(d.get("layers", [])) if "layers" in d else d.get("name"))


def ebro_hosts():
    hosts = [
        "saih.chebro.es", "datos.chebro.es", "saihebro.es", "app.saihebro.es",
        "saihsegura.chsegura.es",
    ]
    for h in hosts:
        for path in ("mapa-niveles", "api/estaciones", ""):
            url = f"https://{h}/{path}".rstrip("/")
            try:
                r = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
                m = re.search(r"let\s+estaciones\s*=", r.text)
                print(url, r.status_code, len(r.text), "EMBED" if m else "")
            except Exception as e:
                print(url, type(e).__name__)


if __name__ == "__main__":
    segura_ivisor()
    print()
    ebro_hosts()
