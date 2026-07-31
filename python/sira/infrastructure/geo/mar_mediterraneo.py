"""Puntos en mar (Mediterráneo occidental) sin invadir tierra."""
from __future__ import annotations

from functools import lru_cache

from sira.infrastructure.geo.bordes_clip import anillos_tierra, punto_en_tierra


def _en_corredor_mar_andalucia(lat: float, lon: float) -> bool:
    """Corredor marítimo Estrecho/Alborán pegado a Andalucía."""
    return 36.00 <= lat <= 36.55 and -5.90 <= lon <= -1.60


def _en_tierra_francia_catalunya(lat: float, lon: float) -> bool:
    """
    Tierra aproximada: interior Cataluña / Rosellón + sur de Francia.

    Corta celdas en la frontera ES-FR (Cerbère / Pirineo) que IGN no siempre detecta.
    """
    if lon < 1.50 or lon > 8.20:
        return False
    if lat < 42.20:
        return False
    # Oeste del Cabo de Creus → tierra (Pirineo / interior).
    if lon < 3.05:
        return lat >= 42.28
    # Portbou / Cerbère: celdas que salían norte de la costa.
    if lon < 3.22:
        return lat >= 42.40
    # Banyuls / Cap Béar (tierra al norte; mar al sur = Cap Creus).
    if lon < 3.45:
        return lat >= 42.48
    if lon < 3.85:
        return lat >= 42.62
    if lon < 4.40:
        return lat >= 42.95
    if lon < 5.30:
        return lat >= 43.05
    if lon < 6.50:
        return lat >= 43.12
    return lat >= 43.18


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
    # Pequeño margen hacia el mar: mejor pintar una celda de más junto a la
    # costa que tapar mar real (huecos en blanco frente a Marruecos/Argelia).
    return lat < _lat_costa_magreb(lon) - 0.04


def _en_tierra_corcega_cerdena(lat: float, lon: float) -> bool:
    """
    Tierra aproximada de Córcega y Cerdeña.

    Franjas estrechas para no comerse el mar alrededor.
    """
    # Córcega.
    if 41.34 <= lat <= 43.02 and 8.52 <= lon <= 9.58:
        return True
    # Cerdeña (franjas N→S).
    if 40.88 <= lat <= 41.26 and 8.48 <= lon <= 9.72:
        return True
    if 40.15 <= lat <= 40.88 and 8.22 <= lon <= 9.68:
        return True
    if 39.35 <= lat <= 40.15 and 8.28 <= lon <= 9.72:
        return True
    if 38.84 <= lat <= 39.35 and 8.38 <= lon <= 9.62:
        return True
    return False


def _en_mar_mediterraneo_west(lat: float, lon: float) -> bool:
    """Envolvente aproximada del Mediterráneo occidental / Alborán."""
    if _en_corredor_mar_andalucia(lat, lon):
        return True
    # Suelo bajado de 35.45 a 34.85: la costa magrebí llega a ~35.0-35.1
    # (Nador, Saidia, Ghazaouet); con 35.45 se excluía mar real frente a
    # Marruecos/Argelia antes de llegar a evaluar _en_tierra_magreb.
    if lat < 34.85 or lat > 43.55 or lon < -6.05 or lon > 10.00:
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


@lru_cache(maxsize=1)
def _anillos_ign() -> list[list[list[float]]]:
    return anillos_tierra()


def punto_en_mar_mediterraneo(lat: float, lon: float) -> bool:
    """True si el punto cae en mar (no tierra) dentro del bbox SST habitual."""
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


def celda_solo_mar(lat: float, lon: float, half: float) -> bool:
    """True si la celda no invade tierra (umbral estricto)."""
    return fraccion_mar_celda(lat, lon, half) >= 0.8


def densificar_celdas_mar(
    celdas: list[dict],
    *,
    paso: float,
    umbral_mar: float = 0.8,
) -> list[dict]:
    """Rellena huecos de mar expandiendo vecinos (solo puntos en mar estricto)."""
    step = round(float(paso), 4)
    half = max(step * 0.48, 0.05)
    idx: dict[tuple[float, float], float] = {}
    for c in celdas:
        if c.get("sst_c") is None:
            continue
        key = (round(float(c["lat"]), 4), round(float(c["lon"]), 4))
        if not punto_en_mar_mediterraneo(key[0], key[1]):
            continue
        if fraccion_mar_celda(key[0], key[1], half) < umbral_mar:
            continue
        idx[key] = float(c["sst_c"])
    if not idx:
        return []

    # Varias pasadas: rellena huecos adyacentes a celdas conocidas.
    for _ in range(6):
        candidatos: dict[tuple[float, float], list[tuple[float, float]]] = {}
        for la, lo in list(idx.keys()):
            for di, dj in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
                nk = (round(la + di * step, 4), round(lo + dj * step, 4))
                if nk in idx:
                    continue
                candidatos.setdefault(nk, []).append((idx[(la, lo)], 1.0))
        added = 0
        for key, vecinos in candidatos.items():
            if len(vecinos) < 2:
                continue
            if not punto_en_mar_mediterraneo(key[0], key[1]):
                continue
            if fraccion_mar_celda(key[0], key[1], half) < umbral_mar:
                continue
            num = sum(val * w for val, w in vecinos)
            den = sum(w for _, w in vecinos)
            idx[key] = round(num / den, 2)
            added += 1
        if added == 0:
            break

    return [{"lat": la, "lon": lo, "sst_c": round(t, 2)} for (la, lo), t in idx.items()]
