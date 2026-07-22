import requests, re
HEADERS = {"User-Agent": "Mozilla/5.0"}
for name in ("submenu_pest2.php", "submenu_pest3.php", "submenu_pest4.php"):
    r = requests.get(f"https://saihweb.chsegura.es/apps/ivisor/{name}", headers=HEADERS, timeout=30)
    zonas = set(re.findall(r"set_punto\('([^']+)'", r.text))
    puntos = re.findall(r"set_punto\('[^']+','([^']+)'\)", r.text)
    print(name, "zonas", zonas, "n_puntos", len(puntos), "sample", puntos[:3])
