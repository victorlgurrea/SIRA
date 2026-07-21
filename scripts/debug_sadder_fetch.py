import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from aforos_segura import parse_sadder_csv
from core import fetch_text

t = fetch_text(
    "https://saihweb.chsegura.es/apps/ivisor/sadder1.php",
    params={"zona": "I", "punto": "01A01", "callVisSerie": "N"},
)
print("len", len(t))
print("csv" in t.lower())
vals = parse_sadder_csv(t)
print("keys", list(vals.keys())[:10])
print("Q02", vals.get("Q02"))
