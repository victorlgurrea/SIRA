"""Puntos en mar Mediterráneo (occidental + centro-oriental) sin invadir tierra."""
from __future__ import annotations

from functools import lru_cache

from sira.infrastructure.geo.bordes_clip import anillos_tierra, punto_en_tierra
from sira.infrastructure.geo.mundo_tierra import punto_en_tierra_mundo


def _en_corredor_mar_andalucia(lat: float, lon: float) -> bool:
    """Corredor marítimo Estrecho/Alborán pegado a Andalucía."""
    return 36.00 <= lat <= 36.55 and -5.90 <= lon <= -1.60


def _en_tierra_francia_catalunya(lat: float, lon: float) -> bool:
    """
    Tierra al norte de la costa mediterránea ES-FR-IT (Cap Creus → Liguria).

    Polilínea de costa (como Magreb): rechaza inland sin comerse el mar abierto.
    Margen inland ~0.03° (~3 km) para que las celdas SST no invadan el basemap.
    """
    if lon < 1.50 or lon > 9.20:
        return False
    if lat < 41.90:
        return False
    return lat > _lat_costa_francia_liguria(lon) + 0.03


# Costa mediterránea Cap Creus → Liguria (lon, lat), oeste→este.
# Ajustada a la orilla real (Golfo de León / Costa Azul) para no dejar mar en blanco.
_COSTA_FRANCIA_LIGURIA: tuple[tuple[float, float], ...] = (
    (1.60, 42.28),  # Cap Creus
    (3.00, 42.48),  # Banyuls / Cerbère
    (3.12, 42.92),  # Leucate
    (3.50, 43.28),  # Narbonne-Plage
    (3.85, 43.42),  # Sète
    (4.10, 43.52),  # La Grande-Motte
    (4.55, 43.42),  # Camargue E
    (5.10, 43.30),  # Oeste Marsella
    (5.40, 43.22),  # Marsella
    (5.90, 43.08),  # Toulon
    (6.35, 43.20),  # Saint-Tropez
    (6.80, 43.42),  # Fréjus
    (7.10, 43.58),  # Cannes
    (7.30, 43.70),  # Antibes / Niza O
    (7.40, 43.75),  # Niza
    (7.60, 43.80),  # Menton
    (8.05, 43.90),  # Sanremo
    (8.55, 44.12),  # Imperia
    (8.95, 44.40),  # Génova
    (9.20, 44.32),  # E Liguria
)


def _lat_costa_francia_liguria(lon: float) -> float:
    """Latitud aproximada de la costa FR/Liguria en una longitud dada."""
    pts = _COSTA_FRANCIA_LIGURIA
    if lon <= pts[0][0]:
        return pts[0][1]
    if lon >= pts[-1][0]:
        return pts[-1][1]
    for (lon0, lat0), (lon1, lat1) in zip(pts, pts[1:]):
        if lon0 <= lon <= lon1:
            if lon1 == lon0:
                return lat0
            t = (lon - lon0) / (lon1 - lon0)
            return lat0 + (lat1 - lat0) * t
    return pts[-1][1]


# Costa mediterránea magrebí: puntos reales aproximados (lon, lat), de oeste a
# este (Estrecho → frontera Túnez/Argelia). Interpolados linealmente para no
# sobrestimar tierra y tapar mar real cerca de la costa (Al Hoceima, Nador,
# Saidia/Ghazaouet bajan hasta lat≈35.0-35.1, muy por debajo de escalones
# anteriores que llegaban a marcar como "tierra" mar real frente a esos tramos).
_COSTA_MAGREB: tuple[tuple[float, float], ...] = (
    (-6.20, 35.90),
    (-5.31, 35.89),  # Ceuta
    (-5.28, 35.68),  # Cabo Negro
    (-5.08, 35.44),  # Oued Laou
    (-4.68, 35.36),  # Targha
    (-3.93, 35.25),  # Al Hoceima
    (-2.95, 35.17),  # Nador
    (-2.24, 35.09),  # Saidia (frontera Marruecos/Argelia)
    (-1.85, 35.10),  # Ghazaouet
    (-1.38, 35.31),  # Beni Saf
    (-0.63, 35.70),  # Orán
    (-0.32, 35.85),  # Arzew
    (0.09, 35.94),  # Mostaganem
    (1.31, 36.52),  # Ténès
    (2.19, 36.60),  # Cherchell
    (3.06, 36.77),  # Argel
    (3.92, 36.92),  # Dellys
    (5.08, 36.75),  # Bejaia
    (5.77, 36.82),  # Jijel
    (6.90, 36.88),  # Skikda
    (7.77, 36.90),  # Annaba
    (8.60, 36.90),  # El Kala
    (9.87, 37.27),  # Biserta
    (10.00, 37.30),
)


def _lat_costa_magreb(lon: float) -> float:
    """Latitud aproximada de la costa magrebí en una longitud dada (interp. lineal)."""
    pts = _COSTA_MAGREB
    if lon <= pts[0][0]:
        return pts[0][1]
    if lon >= pts[-1][0]:
        return pts[-1][1]
    for (lon0, lat0), (lon1, lat1) in zip(pts, pts[1:]):
        if lon0 <= lon <= lon1:
            if lon1 == lon0:
                return lat0
            t = (lon - lon0) / (lon1 - lon0)
            return lat0 + (lat1 - lat0) * t
    return pts[-1][1]


def _en_tierra_magreb(lat: float, lon: float) -> bool:
    """
    Tierra aproximada de Marruecos/Argelia/Túnez mediterráneos.

    IGN solo cubre España; sin esto CMEMS pinta costa magrebí como mar.
    """
    if lat >= 37.35 or lon < -6.2 or lon > 10.0:
        return False
    if _en_corredor_mar_andalucia(lat, lon):
        return False
    # Sin margen hacia el mar: prioriza no pintar tierra (basemap Plotly/NE).
    return lat < _lat_costa_magreb(lon)


def _en_tierra_corcega_cerdena(lat: float, lon: float) -> bool:
    """
    Núcleo de Córcega y Cerdeña (franjas estrechas para no comerse el mar).
    """
    # Córcega (núcleo; deja franja marina en costa W/E).
    if 41.45 <= lat <= 42.95 and 8.70 <= lon <= 9.45:
        return True
    # Cerdeña (núcleo).
    if 40.95 <= lat <= 41.20 and 8.65 <= lon <= 9.55:
        return True
    if 40.25 <= lat <= 40.95 and 8.45 <= lon <= 9.50:
        return True
    if 39.50 <= lat <= 40.25 and 8.50 <= lon <= 9.55:
        return True
    if 38.95 <= lat <= 39.50 and 8.55 <= lon <= 9.45:
        return True
    return False


def _en_mar_mediterraneo_west(lat: float, lon: float) -> bool:
    """Envolvente aproximada del Mediterráneo occidental / Alborán / Liguria."""
    if _en_corredor_mar_andalucia(lat, lon):
        return True
    # Techo 44.55: incluye Costa Azul y mar de Liguria (antes 43.55 dejaba huecos).
    if lat < 34.85 or lat > 44.55 or lon < -6.05 or lon > 10.00:
        return False
    if lat <= 36.90:
        return lon >= -5.90
    if lat <= 38.60:
        return lon >= -3.10
    if lat <= 40.20:
        return lon >= -1.10
    if lat <= 42.35:
        return lon >= 0.10
    return lon >= 1.80


def _en_mar_mediterraneo_este(lat: float, lon: float) -> bool:
    """
    Envolvente amplia del Mediterráneo centro-oriental (Cerdeña → Levante).

    Rectángulo laxo a propósito: aquí no hay heurísticas de costa hechas a
    mano, así que la exclusión de tierra (Italia, Adriático, Grecia, Turquía,
    Chipre, Líbano/Israel/Egipto...) corre a cargo de `anillos_tierra_mediterraneo`
    (Natural Earth). El Mar Negro y el Egeo más al norte quedan fuera del
    dataset CMEMS Med-Physics (llegan como NaN y se descartan antes de
    evaluar esta máscara), así que no hace falta recortarlos aquí.
    """
    return 30.00 <= lat <= 46.00 and 10.00 < lon <= 36.50


@lru_cache(maxsize=1)
def _anillos_ign() -> list[list[list[float]]]:
    return anillos_tierra()


def punto_en_mar_mediterraneo(lat: float, lon: float) -> bool:
    """True si el punto cae en mar (no tierra) dentro del bbox SST habitual."""
    if lon <= 10.00:
        # Mediterráneo occidental: envolvente + heurísticas afinadas a mano
        # (IGN España + Magreb + frontera FR-ES + Córcega/Cerdeña) y Natural Earth
        # para alinear con el basemap Plotly (evita celdas SST sobre tierra blanca).
        if not _en_mar_mediterraneo_west(lat, lon):
            return False
        if punto_en_tierra(lon, lat, _anillos_ign()):
            return False
        if _en_tierra_magreb(lat, lon):
            return False
        if _en_tierra_francia_catalunya(lat, lon):
            return False
        if _en_tierra_corcega_cerdena(lat, lon):
            return False
        if punto_en_tierra_mundo(lat, lon):
            return False
        return True
    # Mediterráneo centro-oriental: envolvente amplia + contorno mundial (indexado).
    if not _en_mar_mediterraneo_este(lat, lon):
        return False
    if punto_en_tierra_mundo(lat, lon):
        # Natural Earth 50m engorda costa: offset a mar abierto => franja costera OK.
        if (
            not punto_en_tierra_mundo(lat - 0.06, lon)
            or not punto_en_tierra_mundo(lat, lon - 0.06)
            or not punto_en_tierra_mundo(lat - 0.04, lon - 0.04)
        ):
            return True
        return False
    return True


def fraccion_mar_celda(lat: float, lon: float, half: float) -> float:
    """Proporción de muestras en mar (centro + esquinas + midpoints de aristas)."""
    h = float(half)
    muestras = [
        (lat, lon),
        (lat - h, lon - h),
        (lat - h, lon + h),
        (lat + h, lon - h),
        (lat + h, lon + h),
        (lat - h, lon),
        (lat + h, lon),
        (lat, lon - h),
        (lat, lon + h),
    ]
    mar = sum(1 for la, lo in muestras if punto_en_mar_mediterraneo(la, lo))
    return mar / len(muestras)


def celda_solo_mar(lat: float, lon: float, half: float, *, umbral: float = 0.9) -> bool:
    """True si la huella de la celda casi no invade tierra."""
    return fraccion_mar_celda(lat, lon, half) >= float(umbral)


def densificar_celdas_mar(
    celdas: list[dict],
    *,
    paso: float,
    umbral_mar: float = 0.85,
    max_celdas: int | None = None,
    solo_costa: bool = False,
) -> list[dict]:
    """Rellena huecos de mar expandiendo vecinos (sin relajar umbral en costa)."""
    step = round(float(paso), 4)
    half = max(step * 0.48, 0.05)
    umbral = float(umbral_mar)
    idx: dict[tuple[float, float], float] = {}
    for c in celdas:
        if c.get("sst_c") is None:
            continue
        key = (round(float(c["lat"]), 4), round(float(c["lon"]), 4))
        if not punto_en_mar_mediterraneo(key[0], key[1]):
            continue
        if fraccion_mar_celda(key[0], key[1], half) < umbral:
            continue
        idx[key] = float(c["sst_c"])
    if not idx:
        return []

    def _cerca_costa_n(lat: float, lon: float) -> bool:
        if 41.5 <= lat <= 44.6 and 2.5 <= lon <= 10.0:
            return True
        if 36.5 <= lat <= 44.5 and 10.0 < lon <= 19.0:
            return True
        return False

    tope = int(max_celdas) if max_celdas and max_celdas > 0 else None
    for _ in range(12):
        if tope is not None and len(idx) >= tope:
            break
        candidatos: dict[tuple[float, float], list[tuple[float, float]]] = {}
        for la, lo in list(idx.keys()):
            for di, dj in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
                nk = (round(la + di * step, 4), round(lo + dj * step, 4))
                if nk in idx:
                    continue
                if solo_costa and not _cerca_costa_n(nk[0], nk[1]):
                    continue
                candidatos.setdefault(nk, []).append((idx[(la, lo)], 1.0))
        added = 0
        for key, vecinos in candidatos.items():
            if tope is not None and len(idx) >= tope:
                break
            if len(vecinos) < 1:
                continue
            if not punto_en_mar_mediterraneo(key[0], key[1]):
                continue
            if fraccion_mar_celda(key[0], key[1], half) < umbral:
                continue
            num = sum(val * w for val, w in vecinos)
            den = sum(w for _, w in vecinos)
            idx[key] = round(num / den, 2)
            added += 1
        if added == 0:
            break

    return [{"lat": la, "lon": lo, "sst_c": round(t, 2)} for (la, lo), t in idx.items()]
