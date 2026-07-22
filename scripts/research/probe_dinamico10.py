import requests, json
HEADERS = {"User-Agent": "Mozilla/5.0"}
base = "https://chsegura.es/server/rest/services/VISOR_CHSIC3/VISOR_PUBLICO_ETRS89_v5_vectorial_dinamico/MapServer/10"
r = requests.get(f"{base}?f=json", timeout=30)
ly = r.json()
print("fields:", [f["name"] for f in ly.get("fields", [])])
r = requests.get(f"{base}/query", params={"where":"1=1","outFields":"*","f":"json","resultRecordCount":"3"}, timeout=60)
data = r.json()
for f in data.get("features", []):
    print(json.dumps(f.get("attributes"), ensure_ascii=False))
