import re, requests
HEADERS = {"User-Agent": "Mozilla/5.0"}
html = requests.get("https://saih.chebro.es/", headers=HEADERS, timeout=30).text
print("estaciones count", html.count("estaciones"))
print("mapa-niveles count", html.count("mapa-niveles"))
scripts = re.findall(r'src=["\']([^"\']+)["\']', html)
print("scripts", len(scripts), scripts[:15])
# inline chunks
for m in re.finditer(r'estaciones', html):
    print("pos", m.start(), html[m.start()-50:m.start()+80])
    break
