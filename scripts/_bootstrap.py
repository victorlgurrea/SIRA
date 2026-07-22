"""Bootstrap sys.path para scripts (añade python/ del repo)."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PYTHON_DIR = _REPO_ROOT / "python"


def ensure_python_path() -> Path:
    """Inserta python/ en sys.path si falta. Devuelve la raíz del repo."""
    p = str(_PYTHON_DIR)
    if p not in sys.path:
        sys.path.insert(0, p)
    return _REPO_ROOT
