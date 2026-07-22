import re, requests
HEADERS = {"User-Agent": "Mozilla/5.0"}
html = requests.get("https://saihweb.chsegura.es/apps/ivisor/index.php?variable=01A01Q02", headers=HEADERS, timeout=30).text
for m in re.finditer(r'<iframe[^>]+>', html, re.I):
    print(m.group(0)[:300])
# default iframe src
for m in re.finditer(r'iframe_izq[^;]{0,200}', html):
    print(m.group(0))
# try visor serie in comunes
for url in [
    "https://saihweb.chsegura.es/apps/comunes/visorSerie/visorSerie.php?variable=01A01Q02&callVisSerie=S",
    "https://saihweb.chsegura.es/apps/comunes/visorSerie/index.php?variable=01A01Q02",
]:
    r = requests.get(url, headers=HEADERS, timeout=30)
    print(url, r.status_code, len(r.text), r.text[:150])
