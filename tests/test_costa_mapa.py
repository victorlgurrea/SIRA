"""Capa costera AEMET en mapa: círculos y tooltips."""
from __future__ import annotations

from sira.domain.costa.mapa import alertas_a_capa_costera


def test_capa_costera_incluye_tooltip_explicativo():
    alertas = [
        {
            "fenomeno": "CO",
            "fenomeno_desc": "fenómeno costero",
            "level": "naranja",
            "zona": "774604",
            "area_desc": "Litoral sur de Valencia",
            "parametro": "Oleaje;Altura;3-4 m",
        },
        {
            "fenomeno": "CO",
            "fenomeno_desc": "fenómeno costero",
            "level": "amarillo",
            "zona": "645404",
            "area_desc": "Sur de Mallorca",
            "parametro": "Oleaje;Altura;2 m",
        },
    ]
    rows = alertas_a_capa_costera(alertas)
    assert len(rows) == 2
    for row in rows:
        html = row.get("hover_html") or ""
        assert "Aviso mar AEMET" in html
        assert "Nivel:" in html
        assert "Zona:" in html
        assert "Radio del aviso" in html
    valencia = next(r for r in rows if "Valencia" in str(r.get("area_desc")))
    assert "naranja" in valencia["hover_html"]
    assert "Oleaje" in valencia["hover_html"] or "3-4" in valencia["hover_html"]
