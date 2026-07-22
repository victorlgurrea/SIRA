import requests
HEADERS = {"User-Agent": "Mozilla/5.0"}
base = "https://saihweb.chsegura.es/apps/comunes/"
names = [
    "APIHidrologia/APIHidrologia.php", "APIHidro/APIHidro.php", "APIDatos/APIDatos.php",
    "APITiempo/APITiempo.php", "datosTiempoReal.php", "ultimosValores.php",
    "visor/datos.php", "php/datosTiempoReal.php",
]
for name in names:
    url = base + name
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        print(name, r.status_code, r.text[:100].replace("\n"," "))
    except Exception as e:
        print(name, e)

# APITiempo with params
r = requests.get(base + "APITiempo/APITiempo.php", headers=HEADERS, timeout=15)
print("APITiempo full", r.text[:300])
