"""Tests calidad del agua costera (sin red)."""
from __future__ import annotations

from sira.services.costa import calidad_agua as mod


def test_madrid_no_es_costera(monkeypatch):
    monkeypatch.setattr(mod, "_es_mar", lambda la, lo: False)
    assert mod.punto_marino_cercano(40.42, -3.70) is None
    assert mod.calidad_agua_local(40.42, -3.70) is None


def test_valencia_encuentra_mar(monkeypatch):
    def fake_mar(la, lo):
        return lo > -0.1 and 39.2 < la < 39.6

    monkeypatch.setattr(mod, "_es_mar", fake_mar)
    pt = mod.punto_marino_cercano(39.47, -0.38)
    assert pt is not None
    assert pt[1] > -0.38


def test_calidad_bwd_es():
    assert mod._calidad_bwd_es("Excellent") == "Excelente"
    assert mod._calidad_bwd_es("Good") == "Buena"
    assert mod._calidad_bwd_es("Poor") == "Insuficiente"


def test_nayade_eea_elige_mas_cercana(monkeypatch):
    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "features": [
                    {
                        "attributes": {
                            "bathingWaterName": "LEJOS",
                            "qualityStatus": "Good",
                            "bwProfileLink": "https://nayadeciudadano.sanidad.gob.es/x",
                            "latitude": 39.60,
                            "longitude": -0.20,
                        }
                    },
                    {
                        "attributes": {
                            "bathingWaterName": "CERCA",
                            "qualityStatus": "Excellent",
                            "bwProfileLink": "https://nayadeciudadano.sanidad.gob.es/y",
                            "latitude": 39.41,
                            "longitude": 0.21,
                        }
                    },
                ]
            }

    monkeypatch.setattr("requests.get", lambda *a, **k: FakeResp())
    out = mod._nayade_eea(39.40, 0.20)
    assert out["playa"] == "CERCA"
    assert out["estado"] == "Excelente"
    assert "nayade" in (out["url"] or "").lower()


def test_calidad_agua_local_mock(monkeypatch):
    monkeypatch.setattr(mod, "punto_marino_cercano", lambda la, lo: (39.40, 0.20))
    monkeypatch.setattr(mod, "_sst_desde_grids", lambda d, la, lo: (24.5, 12))
    monkeypatch.setattr(mod, "_clorofila_noaa", lambda la, lo: (0.22, "2026-09-01"))
    monkeypatch.setattr(
        mod,
        "_nayade_eea",
        lambda la, lo: {
            "estado": "Excelente",
            "detalle": "Clasificación oficial BWD (Náyade → EEA): PLAYA X (2.1 km).",
            "playa": "PLAYA X",
            "url": "https://nayadeciudadano.sanidad.gob.es/",
            "dist_km": 2.1,
            "calidad_raw": "Excellent",
        },
    )
    monkeypatch.setattr(mod, "_cache", {})
    out = mod.calidad_agua_local(
        39.47,
        -0.38,
        dashboard={},
        meteo={"resumen": {"viento_vel": 3.2, "viento_unidad": "m/s", "viento_dir_grados": 90}},
        localidad="Valencia",
    )
    assert out is not None
    assert out["sst_media_c"] == 24.5
    assert out["clorofila_nivel"] == "Baja"
    assert out["turbidez"] == "Agua clara"
    assert out["bano_estado"] == "Excelente"
    assert out["bano_playa"] == "PLAYA X"
    assert "Náyade" in out["aviso"]
    assert out["viento"]["vel_ms"] == 3.2


def test_clorofila_busca_vecinos(monkeypatch):
    calls: list[tuple[float, float]] = []

    def fake_pixel(la, lo):
        calls.append((la, lo))
        # Primer píxel (costa) vacío; el siguiente vecino este tiene dato.
        if len(calls) == 1:
            return None, "2026-09-01"
        return 0.19, "2026-09-01"

    monkeypatch.setattr(mod, "_clorofila_pixel", fake_pixel)
    chl, fecha = mod._clorofila_noaa(39.47, -0.30)
    assert chl == 0.19
    assert fecha == "2026-09-01"
    assert len(calls) > 1
