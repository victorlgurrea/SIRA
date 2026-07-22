"""Overlays de prueba en mapa (varios sismos simultáneos)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / "python"
if str(PYTHON) not in sys.path:
    sys.path.insert(0, str(PYTHON))

import sira.services.overlays.sismo as overlay_mod  # noqa: E402


@pytest.fixture(autouse=True)
def _limpiar_overlay(tmp_path, monkeypatch):
    overlay_file = tmp_path / "test_sismo_overlay.json"
    monkeypatch.setattr(overlay_mod, "TEST_SISMO_OVERLAY_FILE", overlay_file)
    overlay_mod.clear_test_overlay()
    yield
    overlay_mod.clear_test_overlay()


def test_varios_overlays_simultaneos():
    s1 = overlay_mod.build_test_sismo(tag="sira-tsunami-a", tsunami=True, magnitud=7.2)
    s2 = overlay_mod.build_test_sismo(tag="sira-sismo-b", tsunami=False, magnitud=4.5)
    overlay_mod.save_test_overlay(s1, ttl_min=30)
    overlay_mod.save_test_overlay(s2, ttl_min=30)
    activos = overlay_mod.read_test_overlays()
    assert len(activos) == 2
    ids = {s["id"] for s in activos}
    assert s1["id"] in ids
    assert s2["id"] in ids
    assert s1["id"] != s2["id"]


def test_migracion_formato_legacy(monkeypatch, tmp_path):
    overlay_file = tmp_path / "legacy.json"
    monkeypatch.setattr(overlay_mod, "TEST_SISMO_OVERLAY_FILE", overlay_file)
    exp = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    sismo = overlay_mod.build_test_sismo(tag="legacy", magnitud=4.0)
    overlay_file.write_text(
        json.dumps({"expires_at": exp, "sismo": sismo}, ensure_ascii=False),
        encoding="utf-8",
    )
    activos = overlay_mod.read_test_overlays()
    assert len(activos) == 1
    assert activos[0]["id"] == sismo["id"]
