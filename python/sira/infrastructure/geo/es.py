"""Provincias, municipios y localidades de España (INE)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from sira.infrastructure.geo import REPO_ROOT as ROOT
GEO_FILE = ROOT / "data" / "geo" / "espana.json"


def ensure_geo() -> None:
    if not GEO_FILE.is_file():
        from sira.infrastructure.geo import run_build_script

        run_build_script("build_geo_es")


@lru_cache(maxsize=1)
def _data() -> dict:
    ensure_geo()
    return json.loads(GEO_FILE.read_text(encoding="utf-8"))


def provincias() -> list[dict]:
    return _data()["provincias"]


def municipios(provincia_id: str | None) -> list[dict]:
    if not provincia_id:
        return []
    return _data()["municipios"].get(str(provincia_id).zfill(2), [])


def municipio_por_id(municipio_id: str | None) -> dict | None:
    if not municipio_id:
        return None
    mid = str(municipio_id).zfill(5)
    for items in _data()["municipios"].values():
        for m in items:
            if m["id"] == mid:
                return m
    return None


def localidades(municipio_id: str | None) -> list[dict]:
    muni = municipio_por_id(municipio_id)
    if not muni:
        return []
    mid, nombre = muni["id"], muni["nombre"]
    if "/" in nombre:
        return [
            {"id": f"{mid}-{i}", "nombre": parte.strip()}
            for i, parte in enumerate(nombre.split("/"))
            if parte.strip()
        ]
    return [{"id": mid, "nombre": nombre}]


def provincia_de_municipio(municipio_id: str) -> str | None:
    mid = str(municipio_id).zfill(5)
    for pid, items in _data()["municipios"].items():
        if any(m["id"] == mid for m in items):
            return pid
    return None


def provincia_nombre_de_municipio(municipio_id: str | None) -> str | None:
    if not municipio_id:
        return None
    pid = provincia_de_municipio(str(municipio_id))
    if not pid:
        return None
    for p in provincias():
        if str(p.get("id")) == str(pid):
            return p.get("nombre")
    return None


def coords_municipio(municipio_id: str | None) -> tuple[float, float]:
    from sira.config.settings import ZONA

    if not municipio_id:
        return ZONA["lat_ref"], ZONA["lon_ref"]
    muni = municipio_por_id(municipio_id)
    if muni and muni.get("lat") is not None and muni.get("lon") is not None:
        return float(muni["lat"]), float(muni["lon"])
    return ZONA["lat_ref"], ZONA["lon_ref"]


def etiqueta_observacion(municipio_id: str | None, localidad_id: str | None = None) -> str:
    """Nombre legible de la zona de observación (localidad + municipio si aplica)."""
    from sira.config.settings import ZONA

    if not municipio_id:
        return ZONA["ciudad_ref"]
    muni = municipio_por_id(municipio_id)
    if not muni:
        return ZONA["ciudad_ref"]
    locs = localidades(municipio_id)
    if localidad_id:
        lid = str(localidad_id)
        for loc in locs:
            if loc["id"] == lid:
                if len(locs) > 1:
                    return f"{loc['nombre']}, {muni['nombre']}"
                return loc["nombre"]
    return muni["nombre"]


def coords_observacion(
    municipio_id: str | None,
    localidad_id: str | None = None,
) -> tuple[float, float, str]:
    """Coordenadas y etiqueta del punto de observación (centro del municipio)."""
    lat, lon = coords_municipio(municipio_id)
    return lat, lon, etiqueta_observacion(municipio_id, localidad_id)


def opciones(items: list[dict], placeholder: str = "Selecciona…") -> list[dict]:
    if not items:
        return [{"label": placeholder, "value": "__none__", "disabled": True}]
    return [{"label": i["nombre"], "value": str(i["id"])} for i in items]


# Comunidades autónomas → códigos provincia INE (2 dígitos)
CCAA_PROVINCIAS: dict[str, list[str]] = {
    "AN": ["04", "11", "14", "18", "21", "23", "29", "41"],
    "AR": ["22", "44", "50"],
    "AS": ["33"],
    "IB": ["07"],
    "CN": ["35", "38"],
    "CB": ["39"],
    "CL": ["05", "09", "24", "34", "37", "40", "42", "47", "49"],
    "CM": ["02", "13", "16", "19", "45"],
    "CT": ["08", "17", "25", "43"],
    "CE": ["51"],
    "VC": ["03", "12", "46"],
    "EX": ["06", "10"],
    "GA": ["15", "27", "32", "36"],
    "MD": ["28"],
    "ML": ["52"],
    "MC": ["30"],
    "NC": ["31"],
    "RI": ["26"],
    "PV": ["01", "20", "48"],
}

CCAA_NOMBRES: dict[str, str] = {
    "AN": "Andalucía",
    "AR": "Aragón",
    "AS": "Asturias",
    "IB": "Illes Balears",
    "CN": "Canarias",
    "CB": "Cantabria",
    "CL": "Castilla y León",
    "CM": "Castilla-La Mancha",
    "CT": "Cataluña",
    "CE": "Ceuta",
    "VC": "Comunitat Valenciana",
    "EX": "Extremadura",
    "GA": "Galicia",
    "MD": "Madrid",
    "ML": "Melilla",
    "MC": "Murcia",
    "NC": "Navarra",
    "RI": "La Rioja",
    "PV": "País Vasco",
}

PROVINCIA_CCAA: dict[str, str] = {
    prov: ccaa for ccaa, provs in CCAA_PROVINCIAS.items() for prov in provs
}


def ccaa_de_provincia(provincia_id: str | None) -> str | None:
    if not provincia_id:
        return None
    return PROVINCIA_CCAA.get(str(provincia_id).zfill(2))


def ccaa_nombre(ccaa_id: str | None) -> str | None:
    if not ccaa_id:
        return None
    return CCAA_NOMBRES.get(ccaa_id)


def _coords_municipios(provincia_ids: list[str]) -> list[tuple[float, float]]:
    coords: list[tuple[float, float]] = []
    data = _data()
    for pid in provincia_ids:
        for muni in data["municipios"].get(str(pid).zfill(2), []):
            lat, lon = muni.get("lat"), muni.get("lon")
            if lat is not None and lon is not None:
                coords.append((float(lat), float(lon)))
    return coords


def _bounds_from_coords(
    coords: list[tuple[float, float]],
    *,
    pad_ratio: float = 0.14,
    min_pad_lat: float = 0.12,
    min_pad_lon: float = 0.16,
) -> dict[str, float] | None:
    if not coords:
        return None
    lats = [c[0] for c in coords]
    lons = [c[1] for c in coords]
    lat_min, lat_max = min(lats), max(lats)
    lon_min, lon_max = min(lons), max(lons)
    pad_lat = max((lat_max - lat_min) * pad_ratio, min_pad_lat)
    pad_lon = max((lon_max - lon_min) * pad_ratio, min_pad_lon)
    return {
        "lat_centro": (lat_min + lat_max) / 2,
        "lon_centro": (lon_min + lon_max) / 2,
        "lat_min": lat_min - pad_lat,
        "lat_max": lat_max + pad_lat,
        "lon_min": lon_min - pad_lon,
        "lon_max": lon_max + pad_lon,
    }


@lru_cache(maxsize=1)
def _ccaa_bordes_by_id() -> dict[str, dict]:
    path = ROOT / "data" / "geo" / "ccaa_bordes.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {f["id"]: f for f in data.get("features", [])}


def _bounds_ccaa(ccaa_id: str, *, pad_ratio: float, min_pad_lat: float, min_pad_lon: float) -> dict[str, float] | None:
    feat = _ccaa_bordes_by_id().get(ccaa_id)
    if not feat or not feat.get("rings"):
        return None
    coords: list[tuple[float, float]] = []
    for ring in feat["rings"]:
        for lat, lon in zip(ring.get("lat") or [], ring.get("lon") or []):
            coords.append((float(lat), float(lon)))
    return _bounds_from_coords(
        coords,
        pad_ratio=pad_ratio,
        min_pad_lat=min_pad_lat,
        min_pad_lon=min_pad_lon,
    )


def projection_scale_for_viewport(vp: dict, *, margin: float = 1.0) -> float:
    """Escala Mercator coherente con lat y lon del encuadre."""
    import math
    from sira.config.settings import MAPA

    lat_span = max(vp["lat_max"] - vp["lat_min"], 0.5)
    lon_span = max(vp["lon_max"] - vp["lon_min"], 0.5)
    cos_lat = max(math.cos(math.radians(vp["lat_centro"])), 0.35)
    effective = max(lat_span, lon_span * cos_lat) * max(margin, 1.0)
    return min(max(MAPA["projection_scale"] * (11.0 / effective), 1.2), 28.0)


def _clip_viewport(vp: dict[str, float]) -> dict[str, float]:
    from sira.config.settings import MAPA

    nivel = vp.get("nivel")
    lat_min = max(vp["lat_min"], MAPA["lat_min"])
    lat_max = min(vp["lat_max"], MAPA["lat_max"])
    lon_min = max(vp["lon_min"], MAPA["lon_min"])
    lon_max = min(vp["lon_max"], MAPA["lon_max"])
    out = {
        "lat_centro": vp["lat_centro"],
        "lon_centro": vp["lon_centro"],
        "lat_min": lat_min,
        "lat_max": lat_max,
        "lon_min": lon_min,
        "lon_max": lon_max,
    }
    if nivel:
        out["nivel"] = nivel
    if vp.get("centrar_obs"):
        out["centrar_obs"] = True
    return out


def viewport_peninsula() -> dict[str, float]:
    from sira.config.settings import MAPA

    return {
        "lat_centro": MAPA["lat_centro"],
        "lon_centro": MAPA["lon_centro"],
        "lat_min": MAPA["lat_min"],
        "lat_max": MAPA["lat_max"],
        "lon_min": MAPA["lon_min"],
        "lon_max": MAPA["lon_max"],
        "nivel": "peninsula",
    }


def viewport_municipio(municipio_id: str | None) -> dict[str, float]:
    lat, lon = coords_municipio(municipio_id)
    # Menos margen hacia el mar (este en la mayoría de costas peninsulares)
    vp = {
        "lat_centro": lat,
        "lon_centro": lon - 0.04,
        "lat_min": lat - 0.24,
        "lat_max": lat + 0.24,
        "lon_min": lon - 0.28,
        "lon_max": lon + 0.16,
        "nivel": "municipio",
    }
    return _clip_viewport(vp)


def viewport_provincia(provincia_id: str | None, *, alejado: bool = False) -> dict[str, float]:
    if not provincia_id:
        return viewport_peninsula()
    pad_ratio = 0.28 if alejado else 0.22
    min_pad_lat = 0.22 if alejado else 0.16
    min_pad_lon = 0.28 if alejado else 0.20
    bounds = _bounds_from_coords(
        _coords_municipios([str(provincia_id).zfill(2)]),
        pad_ratio=pad_ratio,
        min_pad_lat=min_pad_lat,
        min_pad_lon=min_pad_lon,
    )
    if not bounds:
        return viewport_municipio(None)
    bounds["nivel"] = "provincia"
    return _clip_viewport(bounds)


def viewport_provincia_centro(
    provincia_id: str | None,
    lat_obs: float,
    lon_obs: float,
    *,
    alejado: bool = False,
) -> dict[str, float]:
    """Zoom provincial con el punto de observación (estrella) en el centro."""
    base = viewport_provincia(provincia_id, alejado=alejado)
    lat_span = base["lat_max"] - base["lat_min"]
    lon_span = base["lon_max"] - base["lon_min"]
    vp = {
        "lat_centro": lat_obs,
        "lon_centro": lon_obs,
        "lat_min": lat_obs - lat_span / 2,
        "lat_max": lat_obs + lat_span / 2,
        "lon_min": lon_obs - lon_span / 2,
        "lon_max": lon_obs + lon_span / 2,
        "nivel": "provincia",
        "centrar_obs": True,
    }
    return _clip_viewport(vp)


def viewport_fit_observacion(vp: dict, *, aspect: float = 2.85) -> dict[str, float]:
    """Ajusta el encuadre al contenedor ancho sin desplazar lat_centro/lon_centro."""
    import math

    out = dict(vp)
    lat_c = float(out["lat_centro"])
    lon_c = float(out["lon_centro"])
    nivel = out.get("nivel")

    def _spans(box: dict) -> tuple[float, float, float]:
        lat_span = max(box["lat_max"] - box["lat_min"], 0.01)
        lon_span = max(box["lon_max"] - box["lon_min"], 0.01)
        cos_lat = max(math.cos(math.radians(lat_c)), 0.35)
        return lat_span, lon_span, (lon_span * cos_lat) / lat_span

    lat_span, lon_span, geo_aspect = _spans(out)
    if geo_aspect < aspect:
        need_lon = lat_span * aspect / max(math.cos(math.radians(lat_c)), 0.35)
        out["lon_min"] = lon_c - need_lon / 2
        out["lon_max"] = lon_c + need_lon / 2
    elif geo_aspect > aspect:
        need_lat = lon_span * max(math.cos(math.radians(lat_c)), 0.35) / aspect
        out["lat_min"] = lat_c - need_lat / 2
        out["lat_max"] = lat_c + need_lat / 2

    out["lat_centro"] = lat_c
    out["lon_centro"] = lon_c
    out["centrar_obs"] = True
    if nivel:
        out["nivel"] = nivel
    out = _clip_viewport(out)

    lat_span, lon_span, geo_aspect = _spans(out)
    if geo_aspect < aspect:
        cos_lat = max(math.cos(math.radians(lat_c)), 0.35)
        need_lat = lon_span * cos_lat / aspect
        out["lat_min"] = lat_c - need_lat / 2
        out["lat_max"] = lat_c + need_lat / 2
        out["lat_centro"] = lat_c
        out["lon_centro"] = lon_c
        out["centrar_obs"] = True
        if nivel:
            out["nivel"] = nivel
        out = _clip_viewport(out)

    return out


_CCAA_VALENCIA = "VC"


def es_ccaa_valenciana(provincia_id: str | None) -> bool:
    return ccaa_de_provincia(provincia_id) == _CCAA_VALENCIA


def viewport_mediterraneo_valencia(*, aspect: float = 1.65) -> dict[str, float]:
    """
    Encuadre Comunidad Valenciana + mares (Med occidental, Cantábrico y Atlántico NW).

    lon_min hasta ~-11° para que la malla SST IBI (Galicia/Cantábrico) no quede fuera del recorte.
    """
    vp = {
        "lat_centro": 39.65,
        "lon_centro": -2.25,
        "lat_min": 35.80,
        "lat_max": 44.35,
        "lon_min": -11.15,
        "lon_max": 8.20,
        "nivel": "ccaa",
    }
    return viewport_fit_contenedor(_clip_viewport(vp), aspect=aspect)


def viewport_mapa_geo(
    provincia_id: str | None,
    lat_obs: float,
    lon_obs: float,
    *,
    alejado: bool = True,
    aspect: float = 1.65,
) -> dict[str, float]:
    """Viewport del mapa según provincia/CCAA (Valencia → mar Mediterráneo occidental)."""
    if es_ccaa_valenciana(provincia_id):
        return viewport_mediterraneo_valencia(aspect=aspect)
    return viewport_ccaa_centro(provincia_id, lat_obs, lon_obs, alejado=alejado, aspect=aspect)


def viewport_ccaa_centro(
    provincia_id: str | None,
    lat_obs: float,
    lon_obs: float,
    *,
    alejado: bool = True,
    aspect: float = 2.85,
) -> dict[str, float]:
    """Zoom de comunidad autónoma con la localidad en el centro del mapa."""
    base = viewport_ccaa(provincia_id, alejado=alejado)
    lat_span = base["lat_max"] - base["lat_min"]
    lon_span = base["lon_max"] - base["lon_min"]
    vp = {
        "lat_centro": lat_obs,
        "lon_centro": lon_obs,
        "lat_min": lat_obs - lat_span / 2,
        "lat_max": lat_obs + lat_span / 2,
        "lon_min": lon_obs - lon_span / 2,
        "lon_max": lon_obs + lon_span / 2,
        "nivel": "ccaa",
        "centrar_obs": True,
    }
    return viewport_fit_observacion(_clip_viewport(vp), aspect=aspect)


def viewport_ccaa(provincia_id: str | None, *, alejado: bool = False) -> dict[str, float]:
    ccaa = ccaa_de_provincia(provincia_id)
    if not ccaa:
        return viewport_provincia(provincia_id, alejado=alejado)
    provs = CCAA_PROVINCIAS.get(ccaa, [])
    if len(provs) == 1:
        return viewport_provincia(provs[0], alejado=alejado)
    pad_ratio = 0.75 if alejado else 0.14
    min_pad_lat = 1.55 if alejado else 0.32
    min_pad_lon = 1.30 if alejado else 0.42
    bounds = _bounds_ccaa(ccaa, pad_ratio=pad_ratio, min_pad_lat=min_pad_lat, min_pad_lon=min_pad_lon)
    if not bounds:
        bounds = _bounds_from_coords(
            _coords_municipios(provs),
            pad_ratio=pad_ratio,
            min_pad_lat=min_pad_lat,
            min_pad_lon=min_pad_lon,
        )
    if not bounds:
        return viewport_provincia(provincia_id)
    bounds["nivel"] = "ccaa"
    return _clip_viewport(bounds)


def viewport_para_nivel(
    nivel: str,
    provincia_id: str | None,
    municipio_id: str | None,
    *,
    alejado: bool = False,
) -> dict[str, float]:
    if nivel == "municipio":
        return viewport_municipio(municipio_id)
    if nivel == "provincia":
        return viewport_provincia(provincia_id, alejado=alejado)
    if nivel == "ccaa":
        return viewport_ccaa(provincia_id, alejado=alejado)
    return viewport_peninsula()


def viewport_fit_contenedor(vp: dict, *, aspect: float = 1.65) -> dict:
    """Ajusta lon/lat del encuadre para reducir bandas vacías laterales en el mapa."""
    import math

    out = dict(vp)
    lat_span = max(out["lat_max"] - out["lat_min"], 0.01)
    lon_span = max(out["lon_max"] - out["lon_min"], 0.01)
    cos_lat = max(math.cos(math.radians(out["lat_centro"])), 0.35)
    geo_aspect = (lon_span * cos_lat) / lat_span
    if geo_aspect < aspect:
        need_lon = lat_span * aspect / cos_lat
        extra = (need_lon - lon_span) / 2
        out["lon_min"] -= extra
        out["lon_max"] += extra
    elif geo_aspect > aspect:
        need_lat = lon_span * cos_lat / aspect
        extra = (need_lat - lat_span) / 2
        out["lat_min"] -= extra
        out["lat_max"] += extra
    out["lat_centro"] = (out["lat_min"] + out["lat_max"]) / 2
    out["lon_centro"] = (out["lon_min"] + out["lon_max"]) / 2
    return out


def municipio_mas_cercano(lat: float, lon: float) -> dict | None:
    """Municipio INE más cercano a unas coordenadas WGS84."""
    from sira.domain.geo import distancia_km

    mejor: dict | None = None
    mejor_d = float("inf")
    for items in _data()["municipios"].values():
        for muni in items:
            mlat = muni.get("lat")
            mlon = muni.get("lon")
            if mlat is None or mlon is None:
                continue
            d = distancia_km(lat, lon, float(mlat), float(mlon))
            if d < mejor_d:
                mejor_d = d
                mejor = muni
    if not mejor:
        return None
    pid = provincia_de_municipio(mejor["id"])
    prov = next((p for p in provincias() if p["id"] == pid), None) if pid else None
    return {
        "municipio_id": mejor["id"],
        "municipio": mejor["nombre"],
        "provincia_id": pid,
        "provincia": prov["nombre"] if prov else None,
        "distancia_km": round(mejor_d, 1),
    }
