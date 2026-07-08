"""Utilidades compartidas de parseo meteorológico (ingesta + meteo_live)."""
from __future__ import annotations

from datetime import datetime

VACIO_METEO = {"fuente": "—", "serie_horaria": [], "resumen": {}}

_AEMET_DIR_GRADOS = {
    "N": 0, "NE": 45, "E": 90, "SE": 135, "S": 180, "SO": 225, "O": 270, "NO": 315,
}


def hourly(data: dict, mapping: dict[str, str]) -> list[dict]:
    h = data.get("hourly", {})
    times = h.get("time", [])
    return [
        {"timestamp": t, **{out: h.get(src, [None] * len(times))[i] for out, src in mapping.items()}}
        for i, t in enumerate(times)
    ]


def aemet_val(obj) -> str | int | float | None:
    return obj.get("value") if isinstance(obj, dict) else obj


def num(val, default: float = 0.0) -> float:
    if val is None:
        return default
    s = str(val).strip().lower()
    if s in ("", "ip"):
        return default
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return default


def resumen_lluvia(serie: list[dict]) -> dict:
    s24 = serie[:24]
    probs = [x["prob_precip_pct"] for x in s24 if x.get("prob_precip_pct") is not None]
    return {
        "precip_prox_24h_mm": round(sum(x.get("precip_mm", 0) for x in s24), 1),
        "prob_max_pct": max(probs, default=0),
        "prob_actual_pct": s24[0].get("prob_precip_pct") if s24 else None,
    }


def pack_meteo(fuente: str, municipio: str, serie: list[dict]) -> dict:
    serie = serie[:48]
    return {"fuente": fuente, "municipio": municipio, "serie_horaria": serie, "resumen": resumen_lluvia(serie)}


def _fecha_dia(fecha: str | None) -> str:
    if not fecha:
        return ""
    return str(fecha).split("T")[0]


def _hora_periodo(periodo: str | int | None) -> int | None:
    p = str(periodo or "").strip().rstrip("nN")
    if len(p) == 2 and p.isdigit():
        return int(p)
    return None


def _rango_prob_horas(periodo: str | int | None) -> tuple[int, int] | None:
    p = str(periodo or "").strip()
    if len(p) == 4 and p.isdigit():
        return int(p[:2]), int(p[2:])
    return None


def _aemet_tiempo_codigo(codigo: str | None, descripcion: str = "") -> tuple[str, str]:
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


def _entrada_por_hora(arr: list, hora: int) -> dict | None:
    pstr = f"{hora:02d}"
    for x in arr:
        if not isinstance(x, dict):
            continue
        per = str(x.get("periodo", "")).strip().rstrip("nN")
        if per == pstr:
            return x
    return None


def _parse_aemet_dia_legacy(dia: dict, fecha: str) -> list[dict]:
    serie: list[dict] = []
    for h in dia.get("hora", []):
        periodo = str(h.get("periodo", ""))
        ts = f"{fecha}T{periodo.zfill(2)}:00" if periodo.isdigit() else fecha
        prob = aemet_val(h.get("probPrecipitacion"))
        serie.append({
            "timestamp": ts,
            "precip_mm": num(aemet_val(h.get("precipitacion"))),
            "prob_precip_pct": int(prob) if prob is not None and str(prob).strip().isdigit() else None,
        })
    return serie


def _parse_aemet_dia_arrays(dia: dict, fecha: str) -> list[dict]:
    prob_por_hora: dict[int, int | None] = {}
    for pr in dia.get("probPrecipitacion", []):
        if not isinstance(pr, dict):
            continue
        val = pr.get("value")
        prob = int(val) if val is not None and str(val).strip().isdigit() else None
        rango = _rango_prob_horas(pr.get("periodo"))
        if rango:
            h0, h1 = rango
            for h in range(h0, h1 + 1):
                prob_por_hora[h] = prob

    precip_por_hora: dict[int, float] = {}
    for pr in dia.get("precipitacion", []):
        if not isinstance(pr, dict):
            continue
        h = _hora_periodo(pr.get("periodo"))
        if h is not None:
            precip_por_hora[h] = num(aemet_val(pr.get("value")))

    horas = sorted(set(precip_por_hora) | set(prob_por_hora))
    return [
        {
            "timestamp": f"{fecha}T{h:02d}:00",
            "precip_mm": precip_por_hora.get(h, 0.0),
            "prob_precip_pct": prob_por_hora.get(h),
        }
        for h in horas
    ]


def parse_aemet(data: dict | list) -> list[dict]:
    """Predicción horaria municipal AEMET (formato arrays por día o legacy hora[])."""
    item = (data[0] if isinstance(data, list) else data) or {}
    serie: list[dict] = []
    for dia in item.get("prediccion", {}).get("dia", []):
        if not isinstance(dia, dict):
            continue
        fecha = _fecha_dia(dia.get("fecha"))
        if dia.get("hora"):
            serie.extend(_parse_aemet_dia_legacy(dia, fecha))
        else:
            serie.extend(_parse_aemet_dia_arrays(dia, fecha))
    serie.sort(key=lambda x: x.get("timestamp", ""))
    return serie


def actual_aemet_from_item(item: dict, *, hora: int | None = None) -> dict:
    """Tiempo actual desde bloque horario AEMET (primer día del pronóstico)."""
    dias = item.get("prediccion", {}).get("dia", [])
    if not dias or not isinstance(dias[0], dict):
        return {}
    dia = dias[0]

    if dia.get("hora"):
        horas = dia.get("hora", [])
        if not horas:
            return {}
        h = horas[0]
        cielo = h.get("estadoCielo") or []
        if isinstance(cielo, list) and cielo:
            ec = cielo[0]
            cod = aemet_val(ec.get("value")) if isinstance(ec, dict) else None
            desc = ec.get("descripcion", "") if isinstance(ec, dict) else ""
        else:
            cod, desc = None, ""
        icon, texto = _aemet_tiempo_codigo(str(cod) if cod is not None else None, str(desc))
        temp = num(aemet_val(h.get("temperatura")))
        viento = (h.get("viento") or [{}])[0] if isinstance(h.get("viento"), list) else {}
        vel = num(aemet_val(viento.get("velocidad")), default=-1)
        dirs = viento.get("direccion") or []
        dir_letra = dirs[0] if dirs else None
        hum = num(aemet_val(h.get("humedadRelativa")), default=-1)
        sens = num(aemet_val(h.get("sensTermica")), default=-1)
        return {
            "tiempo_icon": icon,
            "tiempo_texto": texto,
            "temp_c": round(temp, 1) if temp else None,
            "sensacion_c": round(sens, 1) if sens >= 0 else None,
            "humedad_pct": int(round(hum)) if hum >= 0 else None,
            "viento_vel": round(vel, 1) if vel >= 0 else None,
            "viento_unidad": "km/h",
            "viento_dir_grados": _AEMET_DIR_GRADOS.get(str(dir_letra or "").upper()),
            "viento_dir_texto": str(dir_letra).upper() if dir_letra else None,
        }

    h_ref = hora if hora is not None else datetime.now().hour
    ec = _entrada_por_hora(dia.get("estadoCielo", []), h_ref)
    if ec is None:
        cielos = [x for x in dia.get("estadoCielo", []) if isinstance(x, dict)]
        ec = cielos[0] if cielos else None
    temp_o = _entrada_por_hora(dia.get("temperatura", []), h_ref)
    if temp_o is None:
        temps = [x for x in dia.get("temperatura", []) if isinstance(x, dict)]
        temp_o = temps[0] if temps else None
    hum_o = _entrada_por_hora(dia.get("humedadRelativa", []), h_ref)
    sens_o = _entrada_por_hora(dia.get("sensTermica", []), h_ref)

    cod = aemet_val(ec.get("value")) if ec else None
    desc = str(ec.get("descripcion", "")) if ec else ""
    icon, texto = _aemet_tiempo_codigo(str(cod) if cod is not None else None, desc)
    temp = num(aemet_val(temp_o.get("value"))) if temp_o else 0.0

    dir_letra, vel_raw = None, None
    pstr = f"{h_ref:02d}"
    for v in dia.get("vientoAndRachaMax", []):
        if not isinstance(v, dict) or "direccion" not in v:
            continue
        per = str(v.get("periodo", "")).strip().rstrip("nN")
        if per == pstr:
            dirs = v.get("direccion") or []
            vels = v.get("velocidad") or []
            dir_letra = dirs[0] if dirs else None
            vel_raw = vels[0] if vels else None
            break
    vel = num(vel_raw, default=-1)
    hum = num(aemet_val(hum_o.get("value"))) if hum_o else -1
    sens = num(aemet_val(sens_o.get("value"))) if sens_o else -1

    return {
        "tiempo_icon": icon,
        "tiempo_texto": texto,
        "temp_c": round(temp, 1) if temp else None,
        "sensacion_c": round(sens, 1) if sens >= 0 else None,
        "humedad_pct": int(round(hum)) if hum >= 0 else None,
        "viento_vel": round(vel, 1) if vel >= 0 else None,
        "viento_unidad": "km/h",
        "viento_dir_grados": _AEMET_DIR_GRADOS.get(str(dir_letra or "").upper()),
        "viento_dir_texto": str(dir_letra).upper() if dir_letra else None,
    }
