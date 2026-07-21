"""Probe iScada and edaphi for Segura live data."""
from __future__ import annotations

import requests

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/html,*/*"}

urls = [
    "https://saihweb.chsegura.es/apps/iScada/html/inicio/datosTiempoReal.php",
    "https://saihweb.chsegura.es/apps/iScada/html/inicio/getDatos.php",
    "https://saihweb.chsegura.es/apps/iScada/html/inicio/ultimosDatos.php",
    "https://saihweb.chsegura.es/apps/comunes/php/datosTiempoReal.php",
    "https://www.edaphi.es/Segura/datos/saih.json",
    "https://www.edaphi.es/Segura/api/estaciones",
    "https://saihebro.es/wp-json/wp/v2/pages?search=aforo",
]
for url in urls:
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        ct = r.headers.get("content-type", "")
        print(url.split("/")[-1][:40], r.status_code, ct[:30], r.text[:150].replace("\n", " "))
    except Exception as e:
        print(url, e)
