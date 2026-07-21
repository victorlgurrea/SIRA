import re, requests
HEADERS = {"User-Agent": "Mozilla/5.0"}
html = requests.get("https://saihweb.chsegura.es/apps/ivisor/index.php?variable=01A01Q02", headers=HEADERS, timeout=30).text
# find value patterns
for pat in (r'ultimo[^<]{0,80}', r'valor[^<]{0,80}', r'm3/s', r'\d+[.,]\d+\s*m'):
    ms = re.findall(pat, html, re.I)
    print(pat, ms[:5])
# search for JSON in script
for m in re.finditer(r'var\s+\w+\s*=\s*(\{[^;]{50,500}\})', html):
    print("var json", m.group(1)[:300])
