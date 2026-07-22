"""Smoke tests FastAPI — /api/dashboard y /api/status."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from sira.api.server import app


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def dashboard_payload():
    return {
        "generado_en": "2026-07-06T10:30:00+00:00",
        "sismos": [{"id": "test-1", "magnitud": 3.2}],
        "incendios": [],
        "embalses": [],
        "aforos": [],
        "fuentes_estado": {
            "usgs": {"ok": True, "registros": 1},
            "aemet_meteo": {"ok": True, "registros": 1},
        },
    }


def test_api_dashboard(client, dashboard_payload):
    with patch("sira.api.server.read_dashboard", return_value=dashboard_payload):
        r = client.get("/api/dashboard")
    assert r.status_code == 200
    body = r.json()
    assert body["generado_en"] == dashboard_payload["generado_en"]
    assert len(body["sismos"]) == 1


def test_api_status(client, dashboard_payload):
    with (
        patch("sira.api.server.read_dashboard", return_value=dashboard_payload),
        patch("sira.api.server.count_subscriptions", return_value=3),
    ):
        r = client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["suscripciones_push"] == 3
    assert body["fuentes_estado"]["usgs"]["ok"] is True
    assert body["generado_en"] == dashboard_payload["generado_en"]


def test_api_status_sin_datos(client):
    with (
        patch("sira.api.server.read_dashboard", return_value={}),
        patch("sira.api.server.count_subscriptions", return_value=0),
    ):
        r = client.get("/api/status")
    assert r.status_code == 200
    assert r.json()["ok"] is False
