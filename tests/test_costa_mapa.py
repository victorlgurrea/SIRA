"""Avisos costeros AEMET: color por nivel; círculo azul solo tsunami."""
from __future__ import annotations

from sira.domain.costa.mapa import alertas_a_capa_costera, _hover_aviso_mar
from sira.infrastructure.geo.aemet_zonas import NIVEL_COLOR, color_nivel


def test_capa_costera_tooltip_sigue_explicando_aviso():
    alerta = {
        "fenomeno": "CO",
        "fenomeno_desc": "fenómeno costero",
        "level": "naranja",
        "zona": "774604",
        "area_desc": "Litoral sur de Valencia",
        "parametro": "Oleaje;Altura;3-4 m",
    }
    html = _hover_aviso_mar(
        alerta, etiqueta="Fenómeno costero", area="Litoral sur de Valencia", radio=90,
    )
    assert "Aviso mar AEMET" in html
    assert "naranja" in html
    assert "Litoral sur de Valencia" in html


def test_aviso_costero_usa_color_nivel_no_azul():
    """Fenómeno costero se pinta como AEMET (amarillo/naranja/rojo), no azul tsunami."""
    for nivel, rgba in NIVEL_COLOR.items():
        fill, _ = color_nivel(nivel, costera=True)
        assert fill == rgba
        assert "96, 165, 250" not in fill  # azul tsunami


def test_alertas_a_capa_costera_sigue_resolviendo_zonas():
    rows = alertas_a_capa_costera([{
        "fenomeno": "CO",
        "fenomeno_desc": "fenómeno costero",
        "level": "amarillo",
        "zona": "774604",
        "area_desc": "Litoral sur de Valencia",
        "parametro": "Oleaje;Altura;2 m",
    }])
    assert len(rows) == 1
    assert rows[0]["level"] == "amarillo"
    assert "hover_html" in rows[0]
