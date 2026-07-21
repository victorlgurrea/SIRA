import re, requests
HEADERS = {"User-Agent": "Mozilla/5.0"}
html = requests.get("https://saihweb.chsegura.es/apps/ivisor/submenu_pest2.php", headers=HEADERS, timeout=30).text
open("c:/laragon/www/SIRA/scripts/submenu_pest2.html", "w", encoding="utf-8").write(html)
print("written", len(html))
for m in re.finditer(r'\.json|\.php\?[^"\']+', html):
    print(m.group(0)[:100])
