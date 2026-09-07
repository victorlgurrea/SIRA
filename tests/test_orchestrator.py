"""Tests de orquestación de ingesta (fuentes mockeadas)."""
from __future__ import annotations

from sira.services.ingesta import orchestrator as orch
from sira.services.ingesta.source_status import estado_fuente
from sira.infrastructure.sources.hydrology.multi import descargar_aforos_con_estado


def test_estado_fuente_ok_y_error():
    ok_val, ok_st = estado_fuente("Demo", lambda: [1, 2, 3])
    assert ok_val == [1, 2, 3]
    assert ok_st["ok"] is True
    assert ok_st["registros"] == 3

    def boom():
        raise RuntimeError("fallo")

    err_val, err_st = estado_fuente("Demo", boom, default=[])
    assert err_val == []
    assert err_st["ok"] is False
    assert "fallo" in (err_st.get("error") or "")


def test_descargar_sismos_enriquece(monkeypatch):
    feature = {
        "id": "us7000test",
        "properties": {
            "mag": 4.2,
            "place": "Mediterranean Sea",
            "time": 1_700_000_000_000,
            "tsunami": 0,
        },
        "geometry": {"coordinates": [0.2, 39.5, 10.0]},
    }

    def fake_fetch(url, params=None, headers=None):
        if "seismicportal" in str(url):
            return {"features": []}
        return {"features": [feature]}

    monkeypatch.setattr(orch, "fetch_json", fake_fetch)
    sismos = orch.descargar_sismos()
    assert len(sismos) == 1
    s = sismos[0]
    assert s["magnitud"] == 4.2
    assert s["region"]
    assert "dist_valencia_km" in s
    assert "alerta_tsunami" in s


def test_descargar_sismos_incluye_emsc_si_usgs_vacio(monkeypatch):
    emsc = {
        "id": "20260802_0000160",
        "properties": {
            "mag": 4.1,
            "time": "2026-08-02T09:59:25.34Z",
            "flynn_region": "SPAIN",
            "depth": 3.8,
            "unid": "20260802_0000160",
        },
        "geometry": {"coordinates": [-1.4271, 37.9664, -3.8]},
    }

    def fake_fetch(url, params=None, headers=None):
        if "seismicportal" in str(url):
            return {"features": [emsc]}
        return {"features": []}

    monkeypatch.setattr(orch, "fetch_json", fake_fetch)
    sismos = orch.descargar_sismos()
    assert len(sismos) == 1
    assert sismos[0]["magnitud"] == 4.1
    assert sismos[0]["fuente"] == "EMSC"
    assert "Spain" in sismos[0]["lugar"] or "SPAIN" in sismos[0]["lugar"].upper()


def test_descargar_aforos_con_estado_agrega_cuencas(monkeypatch):
    monkeypatch.setattr(
        "sira.infrastructure.sources.hydrology.multi.descargar_aforos_chj",
        lambda *_a, **_k: [{"id": "chj1"}],
    )
    monkeypatch.setattr(
        "sira.infrastructure.sources.hydrology.multi.descargar_aforos_ebro",
        lambda *_a, **_k: [{"id": "che1"}],
    )
    monkeypatch.setattr(
        "sira.infrastructure.sources.hydrology.multi.descargar_aforos_segura",
        lambda *_a, **_k: [],
    )
    # Rebind _CUENCAS fetchers after patch — update module dict
    import sira.infrastructure.sources.hydrology.multi as multi

    multi._CUENCAS = {
        "CHJ": ("saih_chj", lambda *_a, **_k: [{"id": "chj1"}]),
        "CHE": ("saih_che", lambda *_a, **_k: [{"id": "che1"}]),
        "CHS": ("saih_chs", lambda *_a, **_k: []),
    }
    aforos, estados = descargar_aforos_con_estado([], estado_fuente)
    assert len(aforos) == 2
    assert {a["cuenca"] for a in aforos} == {"CHJ", "CHE"}
    assert estados["saih_chj"]["ok"] is True
    assert estados["saih_chs"]["registros"] == 0


def test_ejecutar_ingesta_mock(monkeypatch):
    monkeypatch.setattr(orch, "clear_test_overlay", lambda: None)
    monkeypatch.setattr(orch, "descargar_sismos", lambda: [{
        "id": "t1", "magnitud": 3.0, "lugar": "Test",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "lat": 39.5, "lon": -0.3, "profundidad": 10,
        "dist_valencia_km": 5, "en_mar": False, "es_submarino": False,
        "region": "MEDITERRÁNEO", "usgs_tsunami": 0,
        "alerta_tsunami": False, "radio_tsunami_km": 0.0,
        "score_total": 20, "nivel_alerta": "BAJO",
    }])
    monkeypatch.setattr(orch, "descargar_incendios", lambda: [])
    monkeypatch.setattr(orch, "descargar_embalses", lambda: [])
    monkeypatch.setattr(orch, "_descargar_alertas_cap", lambda: [])
    monkeypatch.setattr(
        orch,
        "descargar_aforos_con_estado",
        lambda alertas, ef: ([], {
            "saih_chj": {"ok": True, "registros": 0, "error": None},
            "saih_che": {"ok": True, "registros": 0, "error": None},
            "saih_chs": {"ok": True, "registros": 0, "error": None},
        }),
    )
    monkeypatch.setattr(
        orch,
        "construir_termico_ccaa",
        lambda *a, **k: {"generado_en": None, "provincias": [], "ccaa": []},
    )
    monkeypatch.setattr(orch, "descargar_oceanografia", lambda: {})
    monkeypatch.setattr(orch, "descargar_sst_med_cuadricula", lambda: {
        "fuente": "CMEMS", "fecha": "2026-01-01", "paso_deg": 0.25,
        "celdas": [{"lat": 39.2, "lon": 0.2, "sst_c": 18.5}],
        "resumen": {"n_celdas": 1, "sst_min_c": 18.5, "sst_max_c": 18.5, "sst_media_c": 18.5},
    })
    monkeypatch.setattr(
        orch,
        "descargar_sst_cant_atl_cuadriculas",
        lambda: (
            {"celdas": [], "resumen": {"n_celdas": 0}},
            {"celdas": [], "resumen": {"n_celdas": 0}},
        ),
    )
    monkeypatch.setattr(orch, "descargar_sst_cant_cuadricula", lambda: {"celdas": []})
    monkeypatch.setattr(orch, "descargar_sst_atl_cuadricula", lambda: {"celdas": []})
    monkeypatch.setattr(orch, "read_dashboard", lambda: {})
    monkeypatch.setattr(orch, "descargar_meteo", lambda: {
        "fuente": "Open-Meteo", "serie_horaria": [{"temp_c": 20}], "resumen": {},
    })
    written: list = []
    monkeypatch.setattr(orch, "write_dashboard", lambda payload: written.append(payload) or "mock.json")
    monkeypatch.setattr(orch, "guardar_snapshots_diarios", lambda *a, **k: None)

    path = orch.ejecutar_ingesta()
    assert path == "mock.json"
    assert written
    out = written[0]
    assert out["estadisticas"]["n_sismos"] == 1
    assert "usgs" in out["fuentes_estado"]
    assert "saih_chj" in out["fuentes_estado"]
    assert out["fuentes_estado"]["usgs"]["ok"] is True
    assert out["fuentes_estado"]["cmems_sst_med"]["ok"] is True
    assert out["fuentes_estado"]["cmems_sst_med"]["registros"] == 1
    assert "cmems_sst_cant" in out["fuentes_estado"]
    assert "cmems_sst_atl" in out["fuentes_estado"]
    assert len(out["sst_med_grid"]["celdas"]) == 1


def test_sst_atl_no_retiene_bbox_obsoleto():
    estrecho = {
        "bbox": {"lat_min": 37.0, "lat_max": 42.3, "lon_min": -10.95, "lon_max": -8.0},
        "celdas": [{"lat": 40.0, "lon": -9.0, "sst_c": 18.0}],
    }
    out = orch._sst_grid_o_previo({}, estrecho, "atl")
    assert out == {}

    completo = {
        "bbox": {"lat_min": 35.9, "lat_max": 42.3, "lon_min": -10.95, "lon_max": -5.0},
        "celdas": [{"lat": 36.2, "lon": -5.5, "sst_c": 19.0}],
    }
    out2 = orch._sst_grid_o_previo({}, completo, "atl")
    assert out2.get("retenido") is True
    assert len(out2["celdas"]) == 1


def test_ibi_timeout_reintenta_atl_separado(monkeypatch):
    monkeypatch.setattr(orch, "CMEMS_SST_REGIONS", {"med", "cant", "atl"})
    monkeypatch.setattr(orch, "clear_test_overlay", lambda: None)
    monkeypatch.setattr(orch, "descargar_sismos", lambda: [])
    monkeypatch.setattr(orch, "descargar_incendios", lambda: [])
    monkeypatch.setattr(orch, "descargar_embalses", lambda: [])
    monkeypatch.setattr(orch, "_descargar_alertas_cap", lambda: [])
    monkeypatch.setattr(
        orch,
        "descargar_aforos_con_estado",
        lambda alertas, ef: ([], {
            "saih_chj": {"ok": True, "registros": 0, "error": None},
            "saih_che": {"ok": True, "registros": 0, "error": None},
            "saih_chs": {"ok": True, "registros": 0, "error": None},
        }),
    )
    monkeypatch.setattr(
        orch,
        "construir_termico_ccaa",
        lambda *a, **k: {"generado_en": None, "provincias": [], "ccaa": []},
    )
    monkeypatch.setattr(orch, "descargar_oceanografia", lambda: {})
    monkeypatch.setattr(orch, "descargar_sst_med_cuadricula", lambda: {
        "fuente": "CMEMS", "fecha": "2026-01-01", "paso_deg": 0.25,
        "celdas": [{"lat": 39.2, "lon": 0.2, "sst_c": 18.5}],
        "resumen": {"n_celdas": 1, "sst_min_c": 18.5, "sst_max_c": 18.5, "sst_media_c": 18.5},
    })

    def boom_ibi():
        raise RuntimeError("CMEMS ibi (cant+atl) superó 240s")

    monkeypatch.setattr(orch, "descargar_sst_cant_atl_cuadriculas", boom_ibi)
    monkeypatch.setattr(
        orch,
        "descargar_sst_atl_cuadricula",
        lambda: {
            "region": "atl",
            "fuente": "CMEMS",
            "fecha": "2026-01-01",
            "paso_deg": 0.08,
            "bbox": {"lat_min": 35.9, "lat_max": 42.3, "lon_min": -10.95, "lon_max": -5.0},
            "celdas": [
                {"lat": 38.7, "lon": -9.5, "sst_c": 17.0},
                {"lat": 36.2, "lon": -5.5, "sst_c": 19.0},
            ],
            "resumen": {"n_celdas": 2, "sst_min_c": 17.0, "sst_max_c": 19.0, "sst_media_c": 18.0},
        },
    )
    monkeypatch.setattr(
        orch,
        "descargar_sst_cant_cuadricula",
        lambda: {
            "region": "cant",
            "fuente": "CMEMS",
            "fecha": "2026-01-01",
            "celdas": [{"lat": 43.4, "lon": -3.8, "sst_c": 16.0}],
            "resumen": {"n_celdas": 1, "sst_min_c": 16.0, "sst_max_c": 16.0, "sst_media_c": 16.0},
        },
    )
    monkeypatch.setattr(orch, "read_dashboard", lambda: {})
    monkeypatch.setattr(orch, "descargar_meteo", lambda: {
        "fuente": "Open-Meteo", "serie_horaria": [{"temp_c": 20}], "resumen": {},
    })
    written: list = []
    monkeypatch.setattr(orch, "write_dashboard", lambda payload: written.append(payload) or "mock.json")
    monkeypatch.setattr(orch, "guardar_snapshots_diarios", lambda *a, **k: None)

    orch.ejecutar_ingesta()
    out = written[0]
    assert out["fuentes_estado"]["cmems_sst_atl"]["ok"] is True
    assert out["fuentes_estado"]["cmems_sst_atl"].get("ibi_fallback_separado") is True
    assert len(out["sst_atl_grid"]["celdas"]) == 2
    assert max(c["lon"] for c in out["sst_atl_grid"]["celdas"]) >= -5.5
