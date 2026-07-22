"""Tests de riesgo_local.py — índice compuesto de impacto."""
from __future__ import annotations

from sira.domain.risks.local import calcular_riesgo_local, _eje_hidrologia, _eje_sismico


def test_eje_sismico_tsunami_prioritario():
    pct, motivo = _eje_sismico([{"alerta_tsunami": True, "score_local": 10}])
    assert pct == 95
    assert "tsunami" in motivo.lower()


def test_eje_hidrologia_bono_lluvia():
    base_pct, _ = _eje_hidrologia({"principales": []}, {"principales": []}, [])
    con_pr_pct, motivo = _eje_hidrologia(
        {"principales": [{"nivel_riesgo": "alerta", "nombre": "Beniarrés"}]},
        {"principales": []},
        [{"fenomeno": "PR", "level": "naranja", "fenomeno_desc": "Lluvia", "area_desc": "Valencia"}],
    )
    assert con_pr_pct > base_pct
    assert con_pr_pct >= 70
    assert "Beniarrés" in motivo
    assert "+15%" in motivo


def test_eje_hidrologia_100_critico_mas_lluvia():
    pct, motivo = _eje_hidrologia(
        {"principales": [{"nivel_riesgo": "critico", "nombre": "Escalona", "porcentaje": 98}]},
        {"principales": []},
        [{"fenomeno": "PR", "fenomeno_desc": "Lluvia"}],
    )
    assert pct == 100
    assert "crítico" in motivo.lower()
    assert "+15%" in motivo


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
        resumen_embalses={"principales": [{"nivel_riesgo": "vigilancia", "nombre": "Test"}]},
        resumen_aforos={"principales": []},
        provincia_id="46",
    )
    assert 0 <= out["indice"] <= 100
    assert out["nivel"]
    assert len(out["ejes"]) == 5
    assert out["ejes"][0]["contrib"] >= out["ejes"][-1]["contrib"]
    for eje in out["ejes"]:
        if eje["pct"] > 0:
            assert eje.get("motivo")
