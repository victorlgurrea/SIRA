import requests, json
HEADERS = {"User-Agent": "Mozilla/5.0"}
base = "https://chsegura.es/server/rest/services/VISOR_CHSIC3/VISOR_PUBLICO_ETRS89_v5_Web_Capas/MapServer"
for lid in (17, 10, 11):
    url = f"{base}/{lid}/query"
    r = requests.get(url, params={
        "where": "1=1", "outFields": "*", "returnGeometry": "true",
        "f": "json", "resultRecordCount": "5",
    }, timeout=60)
    data = r.json()
    feats = data.get("features", [])
    print(f"Layer {lid}: features returned", len(feats), "exceeded", data.get("exceededTransferLimit"))
    if feats:
        print(json.dumps(feats[0].get("attributes"), ensure_ascii=False)[:600])

# paginate layer 10 count
r = requests.get(f"{base}/10/query", params={"where":"1=1","returnCountOnly":"true","f":"json"}, timeout=30)
print("layer 10 count", r.json())
