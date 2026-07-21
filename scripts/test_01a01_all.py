import requests, re, html as htmlmod
HEADERS = {"User-Agent": "Mozilla/5.0"}
r = requests.get("https://saihweb.chsegura.es/apps/ivisor/sadder1.php?zona=I&punto=01A01&callVisSerie=N", headers=HEADERS, timeout=30)
m = re.search(r'id="csv" value="([^"]+)"', r.text)
csv = htmlmod.unescape(m.group(1))
for part in csv.split("***")[2:]:
    print(part)
