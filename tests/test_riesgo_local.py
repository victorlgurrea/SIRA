"""Tests de riesgo_local.py — índice compuesto de impacto."""
from __future__ import annotations

from riesgo_local import calcular_riesgo_local, _eje_hidrologia, _eje_sismico


def test_eje_sismico_tsunami_prioritario():
    assert _eje_sismico([{"alerta_tsunami": True, "score_local": 10}]) == 95


def test_eje_hidrologia_bono_lluvia():
    base = _eje_hidrologia({"principales": []}, {"principales": []}, [])
    con_pr = _eje_hidrologia(
        {"principales": [{"nivel_riesgo": "alerta"}]},
        {"principales": []},
        [{"fenomeno": "PR", "level": "naranja"}],
    )
    assert con_pr > base
    assert con_pr >= 70


def test_calcular_riesgo_local_pondera_ejes():
    out = calcular_riesgo_local(
        alertas_meteo=[{
            "level": "naranja",
            "probabilidad": "70%-100%",
            "fenomeno": "PR",
            "fenomeno_desc": "Lluvia",
            "area_desc": "Valencia",
        }],
        meteo={"fuente": "AEMET", "serie_horaria": [], "resumen": {}},
        sismos=[],
        incendios_local=[],
        resumen_embalses={"principales": [{"nivel_riesgo": "vigilancia"}]},
        resumen_aforos={"principales": []},
        provincia_id="46",
    )
    assert 0 <= out["indice"] <= 100
    assert out["nivel"]
    assert len(out["ejes"]) == 5
    assert out["ejes"][0]["contrib"] >= out["ejes"][-1]["contrib"]
