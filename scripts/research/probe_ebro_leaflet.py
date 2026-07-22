import re, requests
HEADERS = {"User-Agent": "Mozilla/5.0"}
html = requests.get("https://saihebro.es/aforos/", headers=HEADERS, timeout=30).text
# shortcode / leaflet
for m in re.finditer(r'\[leaflet[^\]]+\]', html, re.I):
    print(m.group(0)[:300])
for m in re.finditer(r'leaflet-map[^>]+', html):
    print(m.group(0)[:300])
# markers in inline script
idx = html.find("leaflet")
print("leaflet idx", idx)
print(html[idx:idx+2000] if idx>=0 else "no leaflet text")
