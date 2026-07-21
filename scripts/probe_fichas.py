import re, requests
HEADERS = {"User-Agent": "Mozilla/5.0"}
for url in [
    "https://saihweb.chsegura.es/apps/ivisor/fichas3.php?variable=01A01Q02",
    "https://saihweb.chsegura.es/apps/ivisor/submenu_pest2.php",
    "https://saihweb.chsegura.es/apps/iVisor/inicial.php",
]:
    r = requests.get(url, headers=HEADERS, timeout=30)
    print(url, r.status_code, len(r.text))
    if "m3" in r.text.lower() or "caudal" in r.text.lower():
        for line in r.text.splitlines():
            if any(k in line.lower() for k in ("caudal", "m3", "valor", "01a01")):
                print(" ", line.strip()[:120])
                break
