import requests, re, html as htmlmod
HEADERS = {"User-Agent": "Mozilla/5.0"}

def parse_sadder(zona, punto):
    url = f"https://saihweb.chsegura.es/apps/ivisor/sadder1.php?zona={zona}&punto={punto}&callVisSerie=N"
    r = requests.get(url, headers=HEADERS, timeout=30)
    m = re.search(r'id="csv" value="([^"]+)"', r.text)
    if not m:
        return []
    csv = htmlmod.unescape(m.group(1))
    parts = csv.split("***")
    rows = []
    for part in parts[2:]:
        cols = part.strip().split(";")
        if len(cols) >= 5:
            rows.append({"var": cols[0].strip(), "desc": cols[1].strip(), "fecha": cols[2].strip(), "valor": cols[3].strip(), "uds": cols[5].strip() if len(cols)>5 else ""})
    return rows

for zona, punto in [("I","01A01"), ("I","03A02"), ("II","01A01"), ("01","01A01")]:
    rows = parse_sadder(zona, punto)
    print(zona, punto, len(rows), rows[:2] if rows else "empty")
