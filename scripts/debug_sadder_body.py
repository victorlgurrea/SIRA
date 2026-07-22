import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "scripts"))

from _bootstrap import ensure_python_path

ensure_python_path()

from sira.infrastructure.http.client import fetch_text

t = fetch_text(
    "https://saihweb.chsegura.es/apps/ivisor/sadder1.php",
    params={"zona": "I", "punto": "01A01", "callVisSerie": "N"},
)
print(t)
