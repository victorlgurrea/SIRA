import requests, re
HEADERS = {"User-Agent": "Mozilla/5.0"}
url = "https://saihweb.chsegura.es/apps/ivisor/sadder1.php?zona=I&punto=03A02&callVisSerie=N"
r = requests.get(url, headers=HEADERS, timeout=30)
text = r.text
print("status", r.status_code, "len", len(text))
for line in text.splitlines():
    if any(k in line.lower() for k in ("m3", "caudal", "nivel", "valor", "dato")):
        print(line.strip()[:150])
# numbers
nums = re.findall(r'\d+[.,]\d+', text)
print("nums sample", nums[:20])
