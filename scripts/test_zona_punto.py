import requests, re, html as htmlmod
HEADERS = {"User-Agent": "Mozilla/5.0"}

def parse(zona, punto):
    r = requests.get(f"https://saihweb.chsegura.es/apps/ivisor/sadder1.php?zona={zona}&punto={punto}&callVisSerie=N", headers=HEADERS, timeout=30)
    m = re.search(r'id="csv" value="([^"]+)"', r.text)
    if not m: return None
    csv = htmlmod.unescape(m.group(1))
    header = csv.split("***")[1] if "***" in csv else ""
    return header[:80], len(csv.split("***"))-2

for punto in ["01A02", "01A03", "02A01", "04A01", "06A01"]:
    for zona in ["I", "II", "III", "IV", "V", "VI"]:
        out = parse(zona, punto)
        if out and out[1] > 0:
            print(zona, punto, out)
