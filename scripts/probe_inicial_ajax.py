import re, requests
HEADERS = {"User-Agent": "Mozilla/5.0"}
html = requests.get("https://saihweb.chsegura.es/apps/iVisor/inicial.php", headers=HEADERS, timeout=30).text
for m in re.finditer(r'\$\.ajax\([^)]{0,400}\)', html, re.S):
    print(m.group(0)[:400])
    print("---")
# fichas3
html2 = requests.get("https://saihweb.chsegura.es/apps/ivisor/fichas3.php?variable=01A01Q02", headers=HEADERS, timeout=30).text
print("fichas3 snippet:")
print(html2[3000:5000])
