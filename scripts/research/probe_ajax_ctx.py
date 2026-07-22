import re, requests
HEADERS = {"User-Agent": "Mozilla/5.0"}
html = requests.get("https://saihweb.chsegura.es/apps/ivisor/index.php?variable=01A01Q02", headers=HEADERS, timeout=30).text
idx = html.find("ajax.php")
while idx >= 0:
    print(html[max(0,idx-200):idx+200])
    print("---")
    idx = html.find("ajax.php", idx+1)
