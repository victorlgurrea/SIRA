"""Límite de celdas SST para transporte: debe converger cerca del objetivo
incluso cuando el mar es una franja estrecha dentro de un bbox enorme
(el bug real: el Mediterráneo ocupa una fracción pequeña de su propio
rectángulo lat/lon Europa-Magreb-Levante)."""
from __future__ import annotations

from sira.infrastructure.sources.ocean.sst_transport import limitar_celdas_mapa


def _franja_diagonal(n: int) -> list[dict]:
    """Simula una 'franja de mar' diagonal y estrecha dentro de un bbox
    gigante (como el Mediterráneo dentro de su bbox Europa-Levante)."""
    celdas = []
    for i in range(n):
        t = i / max(n - 1, 1)
        lat = 30.0 + t * 16.5 + (0.3 if i % 2 == 0 else -0.3)
        lon = -6.5 + t * 42.8
        celdas.append({"lat": round(lat, 4), "lon": round(lon, 4), "sst_c": 20.0 + t * 5})
    return celdas


def test_no_reduce_si_ya_esta_bajo_el_limite():
    celdas = _franja_diagonal(100)
    out = limitar_celdas_mapa(celdas, max_n=2600)
    assert out == celdas


def test_converge_cerca_del_objetivo_en_franja_estrecha():
    # ~16000 celdas en una franja diagonal estrecha dentro de un bbox enorme:
    # con el bug antiguo (paso único basado en el área del bbox) esto
    # colapsaba a un ~6% del objetivo (p. ej. 937 de 2600).
    celdas = _franja_diagonal(16000)
    out = limitar_celdas_mapa(celdas, max_n=2600)
    assert len(out) <= 2600
    assert len(out) >= 2600 * 0.85, f"colapsó demasiado: {len(out)} celdas (objetivo ~2600)"


def test_recorta_si_se_pasa_de_limite():
    celdas = [{"lat": 40.0 + i * 0.001, "lon": 0.0 + i * 0.001, "sst_c": 20.0} for i in range(500)]
    out = limitar_celdas_mapa(celdas, max_n=50)
    assert len(out) <= 50
