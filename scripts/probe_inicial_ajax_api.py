import requests, json
HEADERS = {"User-Agent": "Mozilla/5.0"}
url = "https://saihweb.chsegura.es/apps/iVisor/inicial_ajax.php"
for action in ("LeerDatos", "Embalses", "Mapas", "Aforos"):
    r = requests.post(url, data=f"action={action}", headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"}, timeout=60)
    print(action, r.status_code, r.headers.get("content-type"), r.text[:500])
