"""Resumen de avisos en la tarjeta Tiempo ahora."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "dashboard"))
sys.path.insert(0, str(ROOT / "python"))

from ui.components import (  # noqa: E402
    _agrupar_resumen_alertas_tiempo,
    _detalle_alerta_tiempo,
    _zona_alerta_corta,
)


def _parse_dt_fixed(value: str | None):
    from datetime import timezone

    _MADRID = ZoneInfo("Europe/Madrid")
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_MADRID)
    return dt.astimezone(timezone.utc)


def _nivel_rank(level: str | None) -> int:
    return {"amarillo": 1, "naranja": 2, "rojo": 3}.get(str(level or "").lower(), 0)


def _fmt(alerta: dict) -> str:
    return alerta.get("_detalle", "")


def test_zona_alerta_corta_quita_provincia():
    assert _zona_alerta_corta("Litoral sur de Valencia-Valencia/Valencia") == "Litoral sur de Valencia"


def test_detalle_alerta_tiempo_separa_parrafo():
    alerta = {"_detalle": "Temperatura máxima: 40 ºC. En las zonas litorales, aviso."}
    corto, extra = _detalle_alerta_tiempo(alerta, _fmt)
    assert corto == "Temperatura máxima: 40 ºC"
    assert "litorales" in extra


def test_agrupa_zonas_mismo_detalle():
    extra = "En las zonas litorales, el umbral naranja se alcanzará."
    base = {
        "fenomeno": "AT",
        "level": "naranja",
        "onset": "2026-07-14T11:00:00+02:00",
        "expires": "2026-07-14T21:00:00+02:00",
        "_detalle": f"Temperatura máxima: 40 ºC. {extra}",
    }
    alertas = [
        {**base, "area_desc": "Interior norte de Valencia"},
        {**base, "area_desc": "Interior sur de Valencia"},
        {**base, "area_desc": "Litoral norte de Valencia-Valencia/Valencia"},
        {**base, "area_desc": "Litoral sur de Valencia"},
    ]
    lineas = _agrupar_resumen_alertas_tiempo(
        alertas,
        ["2026-07-14T14:00"],
        parse_dt=_parse_dt_fixed,
        nivel_rank=_nivel_rank,
        fmt_detalle=_fmt,
    )
    assert len(lineas) == 1
    nivel, zonas, detalle = lineas[0]
    assert nivel == "naranja"
    assert "Interior norte" in zonas
    assert "Litoral sur" in zonas
    assert detalle.startswith("Temperatura máxima: 40 ºC")
    assert extra in detalle


def test_mantiene_lineas_distintas_por_umbral():
    alertas = [
        {
            "fenomeno": "AT",
            "level": "amarillo",
            "area_desc": "Interior norte de Valencia",
            "onset": "2026-07-14T11:00:00+02:00",
            "expires": "2026-07-14T21:00:00+02:00",
            "_detalle": "Temperatura máxima: 36 ºC",
        },
        {
            "fenomeno": "AT",
            "level": "amarillo",
            "area_desc": "Interior sur de Valencia",
            "onset": "2026-07-14T11:00:00+02:00",
            "expires": "2026-07-14T21:00:00+02:00",
            "_detalle": "Temperatura máxima: 38 ºC",
        },
    ]
    lineas = _agrupar_resumen_alertas_tiempo(
        alertas,
        ["2026-07-14T14:00"],
        parse_dt=_parse_dt_fixed,
        nivel_rank=_nivel_rank,
        fmt_detalle=_fmt,
    )
    assert len(lineas) == 2
