import re, requests, json
HEADERS = {"User-Agent": "Mozilla/5.0"}
html = requests.get("https://saihebro.es/aforos/", headers=HEADERS, timeout=30).text
# leaflet markers
for pat in (r'L\.marker\(', r'geojson', r'latlng', r'fetch\(', r'wp-json', r'\.json'):
    print(pat, len(re.findall(pat, html, re.I)))
# find lat/lon pairs
coords = re.findall(r'"lat"\s*:\s*([0-9.]+).*?"lng"\s*:\s*([0-9.-]+)', html)
print("coords", len(coords), coords[:3])
# leaflet-map data attribute
for m in re.finditer(r'data-[^=]+="[^"]{20,200}"', html):
    s = m.group(0)
    if 'lat' in s.lower() or 'marker' in s.lower():
        print(s[:200])
# rss
rss = requests.get("https://saihebro.es/rsslatest.xml", headers=HEADERS, timeout=30).text
print("RSS:", rss[:800])
