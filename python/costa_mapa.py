"""Zonas costeras AEMET (CO/RI) → círculos en el mapa (avisos de mar / tsunami)."""
from __future__ import annotations

import re
import unicodedata

from config import COSTERO_MAPA, COSTERO_MAP_MAX
from geo_es import coords_municipio

FENOMENOS_COSTEROS_MAPA = frozenset({"CO", "RI"})

# Zonas Meteoalerta con aviso costero (mar=1) · centro aproximado y radio base (km)
_ZONA_COSTERA: dict[str, tuple[float, float, float, str]] = {
    "610403": (36.83, -2.45, 70, "Poniente y Almería Capital"),
    "610404": (37.10, -1.85, 70, "Levante almeriense"),
    "611103": (36.48, -6.25, 75, "Litoral gaditano"),
    "611104": (36.02, -5.35, 80, "Estrecho"),
    "611804": (36.72, -3.45, 70, "Costa granadina"),
    "612103": (37.05, -7.05, 80, "Litoral de Huelva"),
    "612903": (36.62, -4.55, 75, "Sol y Guadalhorce"),
    "612904": (36.72, -4.05, 70, "Axarquía"),
    "633301": (43.58, -6.05, 85, "Litoral occidental asturiano"),
    "633302": (43.52, -5.05, 85, "Litoral oriental asturiano"),
    "645301": (38.90, 1.42, 60, "Ibiza y Formentera"),
    "645401": (39.82, 2.75, 55, "Sierra Tramontana"),
    "645402": (39.92, 3.12, 60, "Norte y nordeste de Mallorca"),
    "645404": (39.38, 2.92, 60, "Sur de Mallorca"),
    "645405": (39.62, 3.32, 55, "Levante mallorquín"),
    "645501": (39.98, 4.05, 55, "Menorca"),
    "659001": (28.12, -15.52, 65, "Norte de Gran Canaria"),
    "659004": (27.92, -15.58, 70, "Gran Canaria sur/oeste"),
    "659101": (29.05, -13.55, 65, "Lanzarote"),
    "659201": (28.38, -14.02, 70, "Fuerteventura"),
    "659303": (28.68, -17.78, 55, "Este de La Palma"),
    "659304": (28.62, -17.92, 55, "Oeste de La Palma"),
    "659401": (28.12, -17.22, 50, "La Gomera"),
    "659501": (27.72, -18.02, 45, "El Hierro"),
    "659601": (28.52, -16.38, 60, "Norte de Tenerife"),
    "659602": (28.32, -16.52, 55, "Área metropolitana de Tenerife"),
    "659603": (28.08, -16.62, 65, "Este, sur y oeste de Tenerife"),
    "663901": (43.48, -3.82, 80, "Litoral cántabro"),
    "690804": (41.32, 2.18, 70, "Litoral de Barcelona"),
    "691703": (42.28, 3.12, 65, "Ampurdán"),
    "691704": (41.78, 3.02, 65, "Litoral sur de Girona"),
    "694303": (41.18, 1.52, 70, "Litoral norte de Tarragona"),
    "694304": (40.78, 0.82, 70, "Litoral sur de Tarragona"),
    "711501": (43.38, -8.48, 90, "Noroeste de A Coruña"),
    "711502": (42.92, -9.02, 85, "Oeste de A Coruña"),
    "711504": (42.48, -9.05, 85, "Suroeste de A Coruña"),
    "712701": (43.68, -7.52, 80, "A Mariña"),
    "713601": (42.22, -8.82, 85, "Rías Baixas"),
    "713603": (42.02, -8.62, 75, "Miño de Pontevedra"),
    "733004": (37.48, -1.02, 75, "Guadalentín y Lorca"),
    "733005": (37.62, -0.92, 75, "Campo de Cartagena"),
    "752001": (43.32, -2.02, 70, "Gipuzkoa litoral"),
    "754801": (43.38, -3.02, 75, "Bizkaia litoral"),
    "770301": (38.48, -0.18, 70, "Litoral norte de Alicante"),
    "770303": (38.02, -0.48, 70, "Litoral sur de Alicante"),
    "771202": (40.48, 0.42, 70, "Litoral norte de Castellón"),
    "771204": (39.92, 0.22, 70, "Litoral sur de Castellón"),
    "774602": (39.62, -0.22, 75, "Litoral norte de Valencia"),
    "774604": (39.22, -0.32, 75, "Litoral sur de Valencia"),
    "785101": (35.88, -5.32, 60, "Ceuta"),
    "795201": (35.28, -2.92, 55, "Melilla"),
}

_SEGMENTOS = (
    {"keywords": ("cantabrico", "cantabria", "asturias", "bizkaia", "gipuzkoa", "pais vasco"), "lat": 43.4, "lon": -3.9, "radio": 90, "nombre": "Cantábrico"},
    {"keywords": ("galicia", "coruna", "pontevedra", "rias"), "lat": 42.6, "lon": -8.7, "radio": 95, "nombre": "Atlántico — Galicia"},
    {"keywords": ("andalucia costa", "cadiz", "huelva", "malaga", "almeria", "estrecho"), "lat": 36.5, "lon": -5.0, "radio": 85, "nombre": "Atlántico — Andalucía"},
    {"keywords": ("murcia", "cartagena", "almeria"), "lat": 37.4, "lon": -1.0, "radio": 75, "nombre": "Levante — Murcia/Almería"},
    {"keywords": ("valencia", "castellon", "castello", "alicante", "alacant"), "lat": 39.4, "lon": -0.2, "radio": 80, "nombre": "Mediterráneo — Valencia"},
    {"keywords": ("balear", "mallorca", "menorca", "ibiza", "formentera", "illes"), "lat": 39.5, "lon": 2.9, "radio": 65, "nombre": "Illes Balears"},
    {"keywords": ("catalu", "catalun", "barcelona", "tarragona", "girona", "ampurdan"), "lat": 41.2, "lon": 2.5, "radio": 75, "nombre": "Mediterráneo — Cataluña"},
    {"keywords": ("canarias", "tenerife", "gran canaria", "lanzarote", "fuerteventura"), "lat": 28.3, "lon": -16.5, "radio": 70, "nombre": "Canarias"},
    {"keywords": ("ceuta", "melilla"), "lat": 35.6, "lon": -4.1, "radio": 55, "nombre": "Ceuta/Melilla"},
)


def _norm_area(value: str | None) -> str:
    if not value:
        return ""
    txt = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return " ".join(txt.strip().lower().split())


def es_alerta_costera_mapa(alerta: dict) -> bool:
    return str(alerta.get("fenomeno") or "").upper().strip() in FENOMENOS_COSTEROS_MAPA


def _oleaje_metros(parametro: str | None) -> float | None:
    if not parametro:
        return None
    raw = str(parametro).lower().replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)\s*m", raw)
    if m:
        return float(m.group(1))
    return None


def radio_costero_km(alerta: dict, radio_base: float | None = None) -> float:
    """Radio del círculo en mapa según nivel AEMET y oleaje/risaga del parámetro."""
    p = COSTERO_MAPA
    base = float(radio_base if radio_base is not None else p["radio_base"])
    level = str(alerta.get("level") or "amarillo").lower()
    factor = p["factor_nivel"].get(level, 1.0)
    radio = base * factor
    oleaje = _oleaje_metros(alerta.get("parametro"))
    if oleaje is not None:
        ref = p["oleaje_ref_m"]
        radio *= max(0.75, min(1.6, oleaje / ref))
    if p["max_km"] > 0:
        radio = min(radio, p["max_km"])
    return round(max(radio, p["min_km"]), 1)


def resolver_zona_costera(alerta: dict) -> dict | None:
    """Devuelve lat, lon, radio_base, clave y nombre para dibujar en el mapa."""
    zona = str(alerta.get("zona") or "").strip()
    if zona.lower().startswith("test-"):
        mid = zona[5:].zfill(5)
        lat, lon = coords_municipio(mid)
        return {
            "lat": lat,
            "lon": lon,
            "radio_base": COSTERO_MAPA["radio_base"],
            "clave": f"test-{mid}",
            "nombre": alerta.get("area_desc") or "Costa (prueba)",
        }

    code = zona.upper().rstrip("C")[:6] if zona else ""
    if code in _ZONA_COSTERA:
        lat, lon, rb, nombre = _ZONA_COSTERA[code]
        return {"lat": lat, "lon": lon, "radio_base": rb, "clave": code, "nombre": nombre}

    area = _norm_area(alerta.get("area_desc"))
    if area:
        for seg in _SEGMENTOS:
            if any(k in area for k in seg["keywords"]):
                return {
                    "lat": seg["lat"],
                    "lon": seg["lon"],
                    "radio_base": seg["radio"],
                    "clave": seg["nombre"],
                    "nombre": alerta.get("area_desc") or seg["nombre"],
                }
    return None


_LEVEL_PRIORIDAD = {"rojo": 3, "naranja": 2, "amarillo": 1}


def alertas_a_capa_costera(alertas: list[dict]) -> list[dict]:
    """Convierte avisos CO/RI activos en filas para círculos azules del mapa."""
    mejor: dict[str, dict] = {}
    for alerta in alertas:
        if not es_alerta_costera_mapa(alerta):
            continue
        zona = resolver_zona_costera(alerta)
        if not zona:
            continue
        radio = radio_costero_km(alerta, zona["radio_base"])
        fen = str(alerta.get("fenomeno") or "CO").upper()
        etiqueta = "Rissaga" if fen == "RI" else "Fenómeno costero"
        row = {
            "lat": zona["lat"],
            "lon": zona["lon"],
            "radio_tsunami_km": radio,
            "magnitud": 0.0,
            "area_desc": alerta.get("area_desc") or zona["nombre"],
            "fenomeno": fen,
            "level": alerta.get("level"),
            "hover_label": f"Aviso mar — {etiqueta}",
        }
        clave = str(zona["clave"])
        prev = mejor.get(clave)
        if not prev or prev["radio_tsunami_km"] < radio:
            mejor[clave] = row
    rows = list(mejor.values())
    rows.sort(
        key=lambda r: (
            -_LEVEL_PRIORIDAD.get(str(r.get("level") or "").lower(), 0),
            -float(r.get("radio_tsunami_km") or 0),
        )
    )
    max_zonas = max(0, int(COSTERO_MAP_MAX))
    return rows[:max_zonas] if max_zonas else []
