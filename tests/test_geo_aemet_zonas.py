"""Zonas Meteoalerta AEMET para el mapa."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from geo_aemet_zonas import aviso_maximo_zona, fenomeno_aplica_zona, zonas_ccaa  # noqa: E402
from geo_aemet_zonas import _aviso_coincide_zona  # noqa: E402


def test_zonas_ccaa_valencia_tiene_tres_provincias():
    zonas = zonas_ccaa("46")
    provs = {z.get("provincia") for z in zonas}
    assert any("Val" in (p or "") for p in provs)
    assert any("Alacant" in (p or "") or "Alicante" in (p or "") for p in provs)
    assert any("Castell" in (p or "") for p in provs)
    assert len(zonas) >= 10


def test_zonas_ccaa_andalucia_amplia():
    zonas = zonas_ccaa("41")
    assert len(zonas) >= 30


def test_aviso_maximo_zona_por_codigo():
    zonas = zonas_ccaa("46")
    zona = next(z for z in zonas if z["id"] and not z.get("costera"))
    aviso = {
        "level": "naranja",
        "fenomeno": "AT",
        "zona": zona["id"],
        "area_desc": zona["nombre"],
        "fenomeno_desc": "temperatura maxima",
        "probabilidad": "40%-70%",
        "parametro": "TA;Temperatura maxima;39 C",
    }
    mejor = aviso_maximo_zona(zona, [aviso])
    assert mejor is not None
    assert mejor["level"] == "naranja"


def test_aviso_temperatura_no_pinta_zona_costera():
    zonas = zonas_ccaa("41")
    costa = next(z for z in zonas if z.get("costera"))
    aviso_at = {
        "level": "amarillo",
        "fenomeno": "AT",
        "zona": costa["id"],
        "area_desc": costa["nombre"],
        "fenomeno_desc": "temperatura maxima",
    }
    assert aviso_maximo_zona(costa, [aviso_at]) is None
    assert fenomeno_aplica_zona("AT", costa) is False
    assert fenomeno_aplica_zona("CO", costa) is True


def test_aviso_costero_pinta_zona_mar():
    zonas = zonas_ccaa("41")
    costa = next(z for z in zonas if z.get("costera"))
    aviso_co = {
        "level": "amarillo",
        "fenomeno": "CO",
        "zona": costa["id"],
        "area_desc": costa["nombre"],
        "fenomeno_desc": "fenomeno costero",
    }
    mejor = aviso_maximo_zona(costa, [aviso_co])
    assert mejor is not None
    assert mejor["fenomeno"] == "CO"


def test_aviso_litoral_tierra_no_matchea_poligono_mar():
    zonas = zonas_ccaa("46")
    costa = next(z for z in zonas if z.get("costera"))
    tierra = next(
        z for z in zonas
        if not z.get("costera") and "litoral" in (z.get("nombre") or "").lower()
    )
    aviso_tierra = {
        "level": "amarillo",
        "fenomeno": "AT",
        "zona": tierra["id"],
        "area_desc": f"{tierra['nombre']}-Valencia/Valencia",
    }
    assert _aviso_coincide_zona(aviso_tierra, tierra)
    assert not _aviso_coincide_zona(aviso_tierra, costa)
    assert aviso_maximo_zona(costa, [aviso_tierra]) is None


def test_aviso_costero_no_pinta_zona_tierra():
    zonas = zonas_ccaa("41")
    tierra = next(z for z in zonas if not z.get("costera"))
    aviso_co = {
        "level": "amarillo",
        "fenomeno": "CO",
        "zona": tierra["id"],
        "area_desc": tierra["nombre"],
        "fenomeno_desc": "fenomeno costero",
    }
    assert aviso_maximo_zona(tierra, [aviso_co]) is None


def test_aviso_maximo_zona_respeta_dia_no_mezcla_manana():
    from datetime import date

    from aemet_alerts import alertas_para_dia  # noqa: E402

    zonas = zonas_ccaa("46")
    zona_int = next(z for z in zonas if str(z.get("id")) == "774601")
    zona_lit = next(z for z in zonas if str(z.get("id")) == "774602")
    alertas = [
        {
            "level": "amarillo",
            "fenomeno": "AT",
            "zona": "774601",
            "area_desc": "Interior norte de Valencia",
            "onset": "2026-07-14T13:00:00+02:00",
            "expires": "2026-07-14T20:59:59+02:00",
        },
        {
            "level": "naranja",
            "fenomeno": "AT",
            "zona": "774601",
            "area_desc": "Interior norte de Valencia",
            "onset": "2026-07-15T13:00:00+02:00",
            "expires": "2026-07-15T20:59:59+02:00",
        },
        {
            "level": "naranja",
            "fenomeno": "AT",
            "zona": "774602",
            "area_desc": "Litoral norte de Valencia",
            "onset": "2026-07-15T13:00:00+02:00",
            "expires": "2026-07-15T20:59:59+02:00",
        },
    ]
    hoy = alertas_para_dia(alertas, dia=date(2026, 7, 14))
    assert aviso_maximo_zona(zona_int, hoy)["level"] == "amarillo"
    assert aviso_maximo_zona(zona_lit, hoy) is None
    assert aviso_maximo_zona(zona_int, alertas)["level"] == "naranja"
