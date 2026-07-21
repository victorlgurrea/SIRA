import re, requests
HEADERS = {"User-Agent": "Mozilla/5.0"}
html = requests.get("https://saihweb.chsegura.es/apps/iVisor/inicial.php", headers=HEADERS, timeout=30).text
actions = set(re.findall(r'action=([A-Za-z0-9_]+)', html))
print("actions", sorted(actions))
url = "https://saihweb.chsegura.es/apps/iVisor/inicial_ajax.php"
for action in sorted(actions):
    r = requests.post(url, data=f"action={action}", headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"}, timeout=60)
    preview = r.text[:120].replace("\n", " ")
    print(action, r.status_code, len(r.text), preview)
