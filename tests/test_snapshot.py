"""Snapshot GitHub no pisa una ingesta más nueva."""
from __future__ import annotations

import gzip
import json

from sira.infrastructure.persistence import snapshot as snap


def test_save_snapshot_no_pisa_disco_mas_nuevo(tmp_path, monkeypatch):
    dest = tmp_path / "dashboard_data.json"
    dest.write_text(
        json.dumps({"generado_en": "2026-09-03T05:57:00+00:00", "sismos": [1]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(snap, "DATA_FILE", dest)

    old = {"generado_en": "2026-09-02T10:40:00+00:00", "sismos": []}
    raw = gzip.compress(json.dumps(old).encode("utf-8"))
    assert snap._save_snapshot_bytes(raw) is True
    kept = json.loads(dest.read_text(encoding="utf-8"))
    assert kept["generado_en"] == "2026-09-03T05:57:00+00:00"


def test_save_snapshot_escribe_si_es_mas_nuevo(tmp_path, monkeypatch):
    dest = tmp_path / "dashboard_data.json"
    dest.write_text(
        json.dumps({"generado_en": "2026-09-02T10:40:00+00:00"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(snap, "DATA_FILE", dest)

    new = {"generado_en": "2026-09-03T05:57:00+00:00", "sismos": [1]}
    raw = gzip.compress(json.dumps(new).encode("utf-8"))
    assert snap._save_snapshot_bytes(raw) is True
    kept = json.loads(dest.read_text(encoding="utf-8"))
    assert kept["generado_en"] == "2026-09-03T05:57:00+00:00"
