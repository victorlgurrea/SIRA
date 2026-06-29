"""Sismo efímero en el mapa tras POST /api/push/test (solo pruebas)."""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timedelta, timezone

from config import TEST_SISMO_OVERLAY_FILE, ZONA
from core import read_json_file
from sismos import distancia_km, distancia_perceptible_km, epicentro_en_mar, radio_tsunami_km, riesgo_tsunami, score_sismo

log = logging.getLogger(__name__)


def _region(lat: float, lon: float) -> str:
    if lat >= 42.5 and lon <= 1.0:
        return "CANTÁBRICO"
    if lon < -5.5:
        return "ATLÁNTICO"
    if lon >= -1.0 or (lat <= 38.0 and lon >= -6.0):
        return "MEDITERRÁNEO"
    return "IBÉRICO"


def _write_overlay(payload: dict) -> None:
    path = TEST_SISMO_OVERLAY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def clear_test_overlay() -> None:
    path = TEST_SISMO_OVERLAY_FILE
    if path.is_file():
        path.unlink(missing_ok=True)


def _epicentro_por_defecto() -> tuple[float, float]:
    """~12 km al E de la referencia de zona (coincide con el texto de prueba)."""
    lat = ZONA["lat_ref"]
    lon = ZONA["lon_ref"] + 12.0 / (111.2 * max(0.2, math.cos(math.radians(lat))))
    return round(lat, 5), round(lon, 5)


def _epicentro_tsunami_prueba() -> tuple[float, float, str]:
    """Epicentro en agua (SE de Valencia) para pruebas de tsunami azul."""
    lat, lon = 38.45, 0.55
    lugar = f"Mediterranean Sea, 55 km SE of {ZONA['ciudad_ref']}"
    return round(lat, 5), round(lon, 5), lugar


def build_test_sismo(
    *,
    tag: str,
    magnitud: float = 4.2,
    lat: float | None = None,
    lon: float | None = None,
    profundidad: float = 10.0,
    lugar: str | None = None,
    simular_real: bool = True,
    tsunami: bool = False,
) -> dict:
    lugar_txt = lugar
    if lat is None or lon is None:
        if tsunami:
            lat, lon, lugar_txt = _epicentro_tsunami_prueba()
        else:
            lat, lon = _epicentro_por_defecto()
    sub = profundidad < 200
    dist_v = distancia_km(lat, lon, ZONA["lat_ref"], ZONA["lon_ref"])
    scores = score_sismo(magnitud, profundidad, dist_v, sub)
    radio = distancia_perceptible_km(magnitud, profundidad)
    usgs_flag = 1 if tsunami else 0
    if not lugar_txt:
        borrador_mar = epicentro_en_mar(
            lat, lon, profundidad_km=profundidad, usgs_tsunami=usgs_flag,
        )
        if borrador_mar:
            lugar_txt = f"Mediterranean Sea, near {ZONA['ciudad_ref']}"
        elif simular_real:
            lugar_txt = f"{dist_v:.0f} km al E of {ZONA['ciudad_ref']}, Spain"
        else:
            lugar_txt = f"{dist_v:.0f} km al E de {ZONA['ciudad_ref']} (prueba)"
    en_mar = epicentro_en_mar(
        lat, lon, lugar=lugar_txt, profundidad_km=profundidad, usgs_tsunami=usgs_flag,
    )
    ts_flag = riesgo_tsunami(magnitud, profundidad, en_mar, usgs_flag)
    radio_ts = radio_tsunami_km(magnitud, profundidad, en_mar=True) if ts_flag else 0.0
    ahora = datetime.now(timezone.utc).isoformat()
    sismo_id = f"sim{tag.replace('sira-', '')[:12]}" if simular_real else f"sira-test-{tag}"
    sismo = {
        "id": sismo_id,
        "magnitud": magnitud,
        "lugar": lugar_txt,
        "timestamp": ahora,
        "lat": lat,
        "lon": lon,
        "profundidad": profundidad,
        "dist_valencia_km": dist_v,
        "radio_perceptible_km": radio,
        "en_mar": en_mar,
        "usgs_tsunami": usgs_flag,
        "alerta_tsunami": ts_flag,
        "radio_tsunami_km": radio_ts,
        "es_submarino": sub,
        "region": _region(lat, lon),
        **scores,
    }
    if not simular_real:
        sismo["es_prueba"] = True
    return sismo


def save_test_overlay(sismo: dict, ttl_min: int = 30) -> dict:
    expires = datetime.now(timezone.utc) + timedelta(minutes=max(1, ttl_min))
    meta = {"expires_at": expires.isoformat(), "sismo": sismo}
    _write_overlay(meta)
    log.info("Overlay de prueba hasta %s → %s", meta["expires_at"], sismo.get("id"))
    return meta


def read_test_overlay() -> dict | None:
    data = read_json_file(TEST_SISMO_OVERLAY_FILE)
    if not data:
        return None
    raw_exp = data.get("expires_at")
    sismo = data.get("sismo")
    if not raw_exp or not isinstance(sismo, dict):
        clear_test_overlay()
        return None
    try:
        expires = datetime.fromisoformat(str(raw_exp).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        clear_test_overlay()
        return None
    if datetime.now(timezone.utc) >= expires:
        clear_test_overlay()
        return None
    return sismo
