import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from core import fetch_text

t = fetch_text(
    "https://saihweb.chsegura.es/apps/ivisor/sadder1.php",
    params={"zona": "I", "punto": "01A01", "callVisSerie": "N"},
)
print(t)
