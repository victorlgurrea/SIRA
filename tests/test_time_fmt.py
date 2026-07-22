"""Formato de hora para UI."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from sira.infrastructure.http.client import fmt_ingesta_local  # noqa: E402


def test_fmt_ingesta_local_fecha_y_hora():
    out = fmt_ingesta_local("2026-07-06T10:30:00+00:00")
    assert out.startswith("06/07/2026 — ")
    assert "12:30" in out or "11:30" in out
    assert "hora España" not in out
    assert "UTC" not in out
