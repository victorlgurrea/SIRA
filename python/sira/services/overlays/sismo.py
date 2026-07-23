"""Sismos efímeros en el mapa tras POST /api/push/test (solo pruebas)."""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timedelta, timezone

from sira.config.settings import TEST_SISMO_OVERLAY_FILE, ZONA
from sira.domain.geo import distancia_km, epicentro_en_mar
from sira.domain.seismic.sismos import (
    distancia_perceptible_km,
    radio_tsunami_km,
    riesgo_tsunami,
    score_sismo,
)

log = logging.getLogger(__name__)


def _region(lat: float, lon: float) -> str:
    if lat >= 42.5 and lon <= 1.0:
        return "CANTÁBRICO"
    if lon < -5.5:
        return "ATLÁNTICO"
    if lon >= -1.0 or (lat <= 38.0 and lon >= -6.0):
        return "MEDITERRÁNEO"
    return "IBÉRICO"


def _write_store(overlays: list[dict]) -> None:
    path = TEST_SISMO_OVERLAY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"overlays": overlays}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def clear_test_overlay() -> None:
    path = TEST_SISMO_OVERLAY_FILE
    if path.is_file():
        path.unlink(missing_ok=True)


def _parse_expires(raw_exp: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(raw_exp).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _read_overlay_entries() -> list[dict]:
    path = TEST_SISMO_OVERLAY_FILE
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    if isinstance(data.get("overlays"), list):
        return [x for x in data["overlays"] if isinstance(x, dict)]
    if isinstance(data.get("sismo"), dict) and data.get("expires_at"):
        return [{"expires_at": data["expires_at"], "sismo": data["sismo"]}]
    return []


def _prune_overlay_entries(entries: list[dict]) -> list[dict]:
    now = datetime.now(timezone.utc)
    valid: list[dict] = []
    for item in entries:
        sismo = item.get("sismo")
        expires = _parse_expires(item.get("expires_at", ""))
        if not isinstance(sismo, dict) or expires is None:
            continue
        if now < expires:
            valid.append(item)
    return valid


def _sync_overlay_file(entries: list[dict]) -> list[dict]:
    valid = _prune_overlay_entries(entries)
    if valid:
        _write_store(valid)
    else:
        clear_test_overlay()
    return valid


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
    safe_tag = "".join(c for c in tag if c.isalnum())[:12] or "test"
    ts_id = int(datetime.now(timezone.utc).timestamp())
    sismo_id = f"sim-{safe_tag}-{ts_id}" if simular_real else f"sira-test-{safe_tag}-{ts_id}"
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
    entries = _prune_overlay_entries(_read_overlay_entries())
    sid = str(sismo.get("id") or "")
    entries = [e for e in entries if str(e.get("sismo", {}).get("id") or "") != sid]
    entries.append(meta)
    _write_store(entries)
    log.info(
        "Overlay de prueba hasta %s → %s (%d activos)",
        meta["expires_at"],
        sismo.get("id"),
        len(entries),
    )
    return meta


def read_test_overlays() -> list[dict]:
    entries = _sync_overlay_file(_read_overlay_entries())
    return [e["sismo"] for e in entries if isinstance(e.get("sismo"), dict)]


def read_test_overlay() -> dict | None:
    overlays = read_test_overlays()
    return overlays[0] if overlays else None
