import re, requests
HEADERS = {"User-Agent": "Mozilla/5.0"}
html = requests.get("https://saihweb.chsegura.es/apps/ivisor/index.php?variable=01A01Q02", headers=HEADERS, timeout=30).text
for m in re.finditer(r'[a-zA-Z0-9_]+\.php[^"\']*', html):
    s = m.group(0)
    if any(k in s.lower() for k in ("serie", "dato", "valor", "vis", "ficha")):
        print(s)
# try serie endpoints
base = "https://saihweb.chsegura.es/apps/ivisor/"
for path in ("serie.php", "visSerie.php", "datosSerie.php", "fichas3.php"):
    for qs in ("?variable=01A01Q02", "?variable=01A01Q02&callVisSerie=S"):
        url = base + path + qs
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code == 200 and len(r.text) > 100:
            print(url, len(r.text), "m3" in r.text.lower() or "caudal" in r.text.lower())
            if "01A01" in r.text:
                for line in r.text.splitlines():
                    if "01A01" in line or "m3" in line.lower():
                        print(" ", line.strip()[:100])
                        break
