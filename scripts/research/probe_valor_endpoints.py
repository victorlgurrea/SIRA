import requests, re
HEADERS = {"User-Agent": "Mozilla/5.0"}
# try variable-specific data endpoints found in CHS apps
var = "01A01Q02"
tests = [
    ("POST", "https://saihweb.chsegura.es/apps/iVisor/inicial_ajax.php", {"action": "LeerDatos", "variable": var}),
    ("POST", "https://saihweb.chsegura.es/apps/iVisor/inicial_ajax.php", {"action": "LeerVariable", "variable": var}),
    ("POST", "https://saihweb.chsegura.es/apps/iVisor/inicial_ajax.php", {"action": "UltimoValor", "codVariable": var}),
    ("GET", f"https://saihweb.chsegura.es/apps/comunes/php/obtenerUltimoValor.php?variable={var}", None),
    ("GET", f"https://saihweb.chsegura.es/apps/comunes/php/ultimoDato.php?codVariableHidrologica={var}", None),
    ("GET", f"https://www.chsegura.es/gestor-de-datos/ultimo-valor?variable={var}", None),
]
for method, url, data in tests:
    if method == "POST":
        r = requests.post(url, data=data, headers=HEADERS, timeout=20)
    else:
        r = requests.get(url, headers=HEADERS, timeout=20)
    print(method, url.split("/")[-1], r.status_code, r.text[:120].replace("\n"," "))
