"""Provincias, municipios y localidades de España (INE)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEO_FILE = ROOT / "data" / "geo" / "espana.json"


def ensure_geo() -> None:
    if not GEO_FILE.is_file():
        from build_geo_es import build

        build()


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
    from config import ZONA

    if not municipio_id:
        return ZONA["lat_ref"], ZONA["lon_ref"]
    muni = municipio_por_id(municipio_id)
    if muni and muni.get("lat") is not None and muni.get("lon") is not None:
        return float(muni["lat"]), float(muni["lon"])
    return ZONA["lat_ref"], ZONA["lon_ref"]


def etiqueta_observacion(municipio_id: str | None, localidad_id: str | None = None) -> str:
    """Nombre legible de la zona de observación (localidad + municipio si aplica)."""
    from config import ZONA

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


def _clip_viewport(vp: dict[str, float]) -> dict[str, float]:
    from config import MAPA

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
    return out


def viewport_peninsula() -> dict[str, float]:
    from config import MAPA

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


def viewport_ccaa(provincia_id: str | None) -> dict[str, float]:
    ccaa = ccaa_de_provincia(provincia_id)
    if not ccaa:
        return viewport_provincia(provincia_id)
    provs = CCAA_PROVINCIAS.get(ccaa, [])
    if len(provs) == 1:
        return viewport_provincia(provs[0])
    bounds = _bounds_from_coords(_coords_municipios(provs), pad_ratio=0.10, min_pad_lat=0.25, min_pad_lon=0.35)
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
        return viewport_ccaa(provincia_id)
    return viewport_peninsula()


def municipio_mas_cercano(lat: float, lon: float) -> dict | None:
    """Municipio INE más cercano a unas coordenadas WGS84."""
    from sismos import distancia_km

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
