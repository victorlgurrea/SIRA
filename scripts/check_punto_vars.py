import requests

H = {"User-Agent": "Mozilla/5.0"}
base = "https://chsegura.es/server/rest/services/VISOR_CHSIC3/VISOR_PUBLICO_ETRS89_v5_vectorial_dinamico/MapServer/10"
fields = "ESRI_OID,CodPuntoMedicion,CodVariableHidrologica,DenominacionVariable"
r = requests.get(
    f"{base}/query",
    params={
        "where": "CodPuntoMedicion LIKE '03A02%'",
        "outFields": fields,
        "returnGeometry": "false",
        "f": "json",
        "resultRecordCount": 20,
    },
    headers=H,
    timeout=60,
)
for f in r.json().get("features", []):
    a = f["attributes"]
    print(a["CodPuntoMedicion"], a["CodVariableHidrologica"], a["DenominacionVariable"][:50])
