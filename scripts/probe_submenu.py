import requests
HEADERS = {"User-Agent": "Mozilla/5.0"}
base = "https://saihweb.chsegura.es/apps/ivisor/"
for url in [
    base + "submenu_pest2.php?variable=01A01Q02",
    base + "submenu_pest2.php?variable=01A01Q02&callVisSerie=S",
    base + "submenu_pest3.php?variable=01A01Q02",
]:
    r = requests.get(url, headers=HEADERS, timeout=30)
    print(url, r.status_code, len(r.text))
    if "m3" in r.text.lower() or "caudal" in r.text.lower() or "valor" in r.text.lower():
        for line in r.text.splitlines():
            ll = line.lower()
            if any(k in ll for k in ("m3", "caudal", "ultimo", "valor")) and "<" in line:
                print(" ", line.strip()[:120])
