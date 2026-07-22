"""Contexto geográfico del dashboard (defaults y resolución de zona)."""
from __future__ import annotations

from sira.config.settings import AEMET_MUNICIPIO
from sira.infrastructure.geo.es import (
    coords_observacion,
    localidades,
    municipio_por_id,
    provincia_de_municipio,
    provincias,
    viewport_ccaa_centro,
)

DEFAULT_MUNI = str(AEMET_MUNICIPIO).zfill(5)
DEFAULT_PROV = provincia_de_municipio(DEFAULT_MUNI) or "46"
_LOCS = localidades(DEFAULT_MUNI)
DEFAULT_LOC = _LOCS[0]["id"] if _LOCS else DEFAULT_MUNI


def default_geo() -> dict:
    muni = municipio_por_id(DEFAULT_MUNI)
    prov = next((p for p in provincias() if p["id"] == DEFAULT_PROV), None)
    loc = _LOCS[0] if _LOCS else None
    lat_obs, lon_obs, _ = coords_observacion(DEFAULT_MUNI, loc["id"] if loc else None)
    return {
        "provincia_id": DEFAULT_PROV,
        "provincia": prov["nombre"] if prov else None,
        "municipio_id": DEFAULT_MUNI,
        "municipio": muni["nombre"] if muni else None,
        "localidad_id": loc["id"] if loc else None,
        "localidad": loc["nombre"] if loc else None,
        "map_zoom": viewport_ccaa_centro(DEFAULT_PROV, lat_obs, lon_obs, alejado=True),
    }


def geo_resuelto(geo: dict | None) -> dict:
    """Geo efectiva del panel: nombres siempre coherentes con los IDs."""
    if not geo:
        return default_geo()

    muni_id = str(geo.get("municipio_id") or DEFAULT_MUNI).zfill(5)
    muni = municipio_por_id(muni_id)
    pid = str(geo.get("provincia_id") or provincia_de_municipio(muni_id) or DEFAULT_PROV).zfill(2)
    prov = next((p for p in provincias() if p["id"] == pid), None)
    locs = localidades(muni_id)
    loc_id = geo.get("localidad_id")
    loc = next((l for l in locs if l["id"] == loc_id), locs[0] if locs else None)

    out = {
        "provincia_id": pid,
        "provincia": prov["nombre"] if prov else geo.get("provincia"),
        "municipio_id": muni_id,
        "municipio": muni["nombre"] if muni else geo.get("municipio"),
        "localidad_id": loc["id"] if loc else geo.get("localidad_id"),
        "localidad": loc["nombre"] if loc else geo.get("localidad"),
    }
    zoom = geo.get("map_zoom")
    if zoom:
        out["map_zoom"] = zoom
    else:
        lat_obs, lon_obs, _ = coords_observacion(muni_id, out.get("localidad_id"))
        out["map_zoom"] = viewport_ccaa_centro(pid, lat_obs, lon_obs, alejado=True)
    return out


def theme_val(theme: str | None) -> str:
    return "light" if theme == "light" else "dark"
