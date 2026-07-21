"""Probe Segura ajax.php for live values."""
from __future__ import annotations

import re
import requests

HEADERS = {"User-Agent": "Mozilla/5.0"}
base = "https://saihweb.chsegura.es/apps/ivisor"
html = requests.get(f"{base}/index.php?variable=01A01Q02", headers=HEADERS, timeout=30).text
# find ajax.php calls
for m in re.finditer(r"ajax\.php[^'\"]*", html):
    print("ref", m.group(0)[:120])
for m in re.finditer(r"url\s*:\s*['\"]([^'\"]+)['\"]", html):
    u = m.group(1)
    if "ajax" in u or "php" in u:
        print("url", u)

# try common ajax.php params
ajax_url = f"{base}/ajax.php"
for params in [
    {"variable": "01A01Q02"},
    {"codVariable": "01A01Q02"},
    {"codigo": "01A01Q02", "accion": "ultimo"},
    {"variable": "01A01Q02", "tipo": "ultimo"},
]:
    r = requests.get(ajax_url, params=params, headers=HEADERS, timeout=30)
    print("GET", params, r.status_code, r.text[:200])

for data in [
    {"variable": "01A01Q02"},
    {"codVariableHidrologica": "01A01Q02"},
]:
    r = requests.post(ajax_url, data=data, headers=HEADERS, timeout=30)
    print("POST", data, r.status_code, r.text[:200])
