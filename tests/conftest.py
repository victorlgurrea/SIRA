"""Configuración pytest — añade python/ al path."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for subdir in ("python", "dashboard"):
    p = str(ROOT / subdir)
    if p not in sys.path:
        sys.path.insert(0, p)
