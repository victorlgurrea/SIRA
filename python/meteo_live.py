"""Meteorología en tiempo real para un municipio/localidad."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from config import AEMET_API_KEY, FORECAST_DAYS, OPEN_METEO_WEATHER_URL, ZONA
from core import fetch_aemet, fetch_json
from geo_es import coords_municipio, municipio_por_id
from meteo_parse import (
    VACIO_METEO,
    actual_aemet_from_item,
    hourly as _hourly,
    num as _num,
    parse_aemet as _parse_aemet,
    resumen_lluvia as _resumen_lluvia,
)

log = logging.getLogger(__name__)

_AEMET_DIR_GRADOS = {
    "N": 0, "NE": 45, "E": 90, "SE": 135, "S": 180, "SO": 225, "O": 270, "NO": 315,
}

_MADRID_TZ = ZoneInfo("Europe/Madrid")


def _wmo_tiempo(code: int | None) -> tuple[str, str]:
    if code is None:
        return "🌡️", "—"
    c = int(code)
    if c == 0:
        return "☀️", "Despejado"
    if c in (1, 2):
        return "🌤️", "Poco nuboso"
    if c == 3:
        return "☁️", "Nuboso"
    if c in (45, 48):
        return "🌫️", "Niebla"
    if c in (51, 53, 55, 56, 57):
        return "🌦️", "Llovizna"
    if c in (61, 63, 65, 66, 67, 80, 81, 82):
        return "🌧️", "Lluvia"
    if c in (71, 73, 75, 77, 85, 86):
        return "🌨️", "Nieve"
    if c in (95, 96, 99):
        return "⛈️", "Tormenta"
    return "☁️", "Nuboso"


def _aemet_tiempo(codigo: str | None, descripcion: str = "") -> tuple[str, str]:
    desc = (descripcion or "").lower()
    if "tormenta" in desc:
        return "⛈️", descripcion or "Tormenta"
    if "lluvia" in desc or "chubasco" in desc:
        return "🌧️", descripcion or "Lluvia"
    if "nieve" in desc:
        return "🌨️", descripcion or "Nieve"
    if "niebla" in desc or "bruma" in desc:
        return "🌫️", descripcion or "Niebla"
    c = str(codigo or "").strip()
    if c in ("11",):
        return "☀️", descripcion or "Despejado"
    if c in ("12", "17"):
        return "🌤️", descripcion or "Poco nuboso"
    if c in ("13", "23", "43"):
        return "🌥️", descripcion or "Intervalos nubosos"
    if c in ("14", "24", "44"):
        return "☁️", descripcion or "Nuboso"
    if c in ("15", "25", "45"):
        return "☁️", descripcion or "Muy nuboso"
    if c in ("16",):
        return "☁️", descripcion or "Cubierto"
    return "🌡️", descripcion or "—"


def _aemet_dir_grados(letra: str | None) -> float | None:
    if not letra:
        return None
    return _AEMET_DIR_GRADOS.get(str(letra).strip().upper())


def _actual_openmeteo(data: dict) -> dict:
    cur = data.get("current") or {}
    code = cur.get("weather_code")
    icon, texto = _wmo_tiempo(code)
    temp = cur.get("temperature_2m")
    vel = cur.get("wind_speed_10m")
    sens = cur.get("apparent_temperature")
    hum = cur.get("relative_humidity_2m")
    return {
        "tiempo_icon": icon,
        "tiempo_texto": texto,
        "temp_c": round(float(temp), 1) if temp is not None else None,
        "sensacion_c": round(float(sens), 1) if sens is not None else None,
        "humedad_pct": int(round(float(hum))) if hum is not None else None,
        "viento_vel": round(float(vel), 1) if vel is not None else None,
        "viento_unidad": "m/s",
        "viento_dir_grados": cur.get("wind_direction_10m"),
    }


def _actual_aemet(item: dict) -> dict:
    return actual_aemet_from_item(item)


def _proximas_horas_desde_serie(serie: list[dict], *, horas: int = 6) -> list[dict]:
    """Próximas horas con temperatura desde una serie horaria normalizada."""
    ahora = datetime.now(_MADRID_TZ)
    corte = ahora.replace(minute=0, second=0, microsecond=0)
    if ahora.minute or ahora.second or ahora.microsecond:
        corte = corte + timedelta(hours=1)

    out: list[dict] = []
    for row in sorted(serie, key=lambda x: str(x.get("timestamp") or "")):
        if not isinstance(row, dict):
            continue
        ts = str(row.get("timestamp") or "")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_MADRID_TZ)
            else:
                dt = dt.astimezone(_MADRID_TZ)
        except ValueError:
            continue
        if dt < corte:
            continue
        temp = row.get("temp_c")
        sens = row.get("sensacion_c")
        if temp is None and sens is None:
            continue
        out.append({
            "timestamp": dt.strftime("%Y-%m-%dT%H:%M"),
            "temp_c": round(float(temp), 1) if temp is not None else None,
            "sensacion_c": round(float(sens), 1) if sens is not None else None,
        })
        if len(out) >= horas:
            break
    return out


def _aemet_proximas_horas(item: dict, *, horas: int = 6) -> list[dict]:
    """Bloque horario de temperatura AEMET desde la próxima hora local."""
    dias = item.get("prediccion", {}).get("dia", [])
    if not isinstance(dias, list):
        return []

    ahora = datetime.now(_MADRID_TZ)
    corte = ahora.replace(minute=0, second=0, microsecond=0)
    if ahora.minute or ahora.second or ahora.microsecond:
        corte = corte + timedelta(hours=1)

    out: list[dict] = []

    for dia in dias:
        if not isinstance(dia, dict):
            continue
        fecha = str(dia.get("fecha") or "").split("T")[0]
        if not fecha:
            continue

        # Formato legacy: dia["hora"] con objetos por hora
        if isinstance(dia.get("hora"), list) and dia.get("hora"):
            for h in dia.get("hora", []):
                if not isinstance(h, dict):
                    continue
                per = str(h.get("periodo") or "").strip()
                if not per.isdigit():
                    continue
                dt_txt = f"{fecha}T{per.zfill(2)}:00"
                try:
                    dt = datetime.fromisoformat(dt_txt).replace(tzinfo=_MADRID_TZ)
                except ValueError:
                    continue
                if dt < corte:
                    continue
                temp = _num(h.get("temperatura"), default=-999)
                sens = _num(h.get("sensTermica"), default=-999)
                out.append({
                    "timestamp": dt.strftime("%Y-%m-%dT%H:%M"),
                    "temp_c": round(temp, 1) if temp > -900 else None,
                    "sensacion_c": round(sens, 1) if sens > -900 else None,
                })
        else:
            # Formato arrays por día: temperatura/sensTermica con periodo+value
            temp_by_h: dict[int, float | None] = {}
            sens_by_h: dict[int, float | None] = {}
            for t in dia.get("temperatura", []) or []:
                if not isinstance(t, dict):
                    continue
                per = str(t.get("periodo") or "").strip().rstrip("nN")
                if per.isdigit():
                    h = int(per)
                    if 0 <= h <= 23:
                        v = _num(t.get("value"), default=-999)
                        temp_by_h[h] = round(v, 1) if v > -900 else None
            for s in dia.get("sensTermica", []) or []:
                if not isinstance(s, dict):
                    continue
                per = str(s.get("periodo") or "").strip().rstrip("nN")
                if per.isdigit():
                    h = int(per)
                    if 0 <= h <= 23:
                        v = _num(s.get("value"), default=-999)
                        sens_by_h[h] = round(v, 1) if v > -900 else None

            for h in sorted(temp_by_h.keys() | sens_by_h.keys()):
                dt_txt = f"{fecha}T{h:02d}:00"
                try:
                    dt = datetime.fromisoformat(dt_txt).replace(tzinfo=_MADRID_TZ)
                except ValueError:
                    continue
                if dt < corte:
                    continue
                out.append({
                    "timestamp": dt.strftime("%Y-%m-%dT%H:%M"),
                    "temp_c": temp_by_h.get(h),
                    "sensacion_c": sens_by_h.get(h),
                })

        if len(out) >= horas:
            break

    out.sort(key=lambda x: x.get("timestamp", ""))
    return out[:horas]


def _pack_local(
    fuente: str,
    municipio: str,
    serie: list[dict],
    actual: dict,
    *,
    proximas_horas: list[dict] | None = None,
) -> dict:
    resumen = {**_resumen_lluvia(serie), **actual}
    return {
        "fuente": fuente,
        "municipio": municipio,
        "serie_horaria": serie[:48],
        "resumen": resumen,
        "proximas_horas": proximas_horas or [],
    }


def meteo_localidad(municipio_id: str | None, localidad: str | None = None) -> dict:
    if not municipio_id:
        return VACIO_METEO

    muni = municipio_por_id(municipio_id)
    nombre = localidad or (muni["nombre"] if muni else ZONA["ciudad_ref"])
    codigo = str(municipio_id).zfill(5)

    if AEMET_API_KEY:
        try:
            data = fetch_aemet(f"prediccion/especifica/municipio/horaria/{codigo}", AEMET_API_KEY)
            item = (data[0] if isinstance(data, list) else data) or {}
            serie = _parse_aemet(data)
            if serie:
                prox = _aemet_proximas_horas(item, horas=6)
                if not prox:
                    prox = _proximas_horas_desde_serie(serie, horas=6)
                return _pack_local(
                    "AEMET",
                    item.get("nombre", nombre),
                    serie,
                    _actual_aemet(item),
                    proximas_horas=prox,
                )
        except (requests.RequestException, ValueError, OSError) as exc:
            log.warning("AEMET %s: %s", codigo, exc)

    try:
        lat, lon = coords_municipio(municipio_id)
        data = fetch_json(OPEN_METEO_WEATHER_URL, {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,wind_direction_10m",
            "hourly": "temperature_2m,apparent_temperature,precipitation,precipitation_probability",
            "wind_speed_unit": "ms",
            "timezone": "Europe/Madrid",
            "forecast_days": FORECAST_DAYS,
        })
        serie = _hourly(data, {
            "temp_c": "temperature_2m",
            "sensacion_c": "apparent_temperature",
            "precip_mm": "precipitation",
            "prob_precip_pct": "precipitation_probability",
        })
        for row in serie:
            row["precip_mm"] = row.get("precip_mm") or 0.0
            if row.get("temp_c") is not None:
                row["temp_c"] = round(float(row["temp_c"]), 1)
            if row.get("sensacion_c") is not None:
                row["sensacion_c"] = round(float(row["sensacion_c"]), 1)
        return _pack_local(
            "Open-Meteo",
            nombre,
            serie,
            _actual_openmeteo(data),
            proximas_horas=_proximas_horas_desde_serie(serie, horas=6),
        )
    except (requests.RequestException, ValueError, OSError) as exc:
        log.warning("Open-Meteo %s: %s", codigo, exc)
        return VACIO_METEO
