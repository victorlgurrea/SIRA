import requests, re, html as htmlmod
HEADERS = {"User-Agent": "Mozilla/5.0"}
r = requests.get("https://saihweb.chsegura.es/apps/ivisor/sadder1.php?zona=I&punto=03A02&callVisSerie=N", headers=HEADERS, timeout=30)
text = r.text
m = re.search(r'id="csv" value="([^"]+)"', text)
if m:
    csv = htmlmod.unescape(m.group(1))
    print("CSV:", csv[:500])
# table rows with values
rows = re.findall(r"<tr[^>]*>.*?VALOR.*?</tr>", text, re.S | re.I)
print("rows", len(rows))
for tr in re.findall(r"<tr onMouseOver[^>]*>.*?</tr>", text, re.S)[:5]:
    cells = re.findall(r">([^<]+)<", tr)
    print("cells", [c.strip() for c in cells if c.strip()][:6])
