"""Selector geográfico España (provincia → municipio → localidad)."""
from __future__ import annotations

from dash import dcc, html

from geo_es import localidades, municipios, opciones, provincias


def selector_geo(
    prov_id: str = "",
    muni_id: str = "",
    loc_id: str = "",
) -> html.Div:
    prov_opts = opciones(provincias(), "Provincia")
    muni_opts = opciones(municipios(prov_id), "Municipio") if prov_id else opciones([], "Municipio")
    loc_opts = opciones(localidades(muni_id), "Localidad") if muni_id else opciones([], "Localidad")

    return html.Div(className="sira-geo-bar", children=[
        html.Span("Ubicación en España", className="sira-geo-label"),
        html.Div(className="sira-geo-fields", children=[
            html.Div(className="sira-geo-field", children=[
                html.Label("Provincia", className="sira-geo-field-label", htmlFor="geo-provincia"),
                dcc.Dropdown(
                    id="geo-provincia",
                    options=prov_opts,
                    value=prov_id or None,
                    placeholder="Provincia",
                    clearable=False,
                    className="sira-geo-select",
                ),
            ]),
            html.Div(className="sira-geo-field", children=[
                html.Label("Municipio", className="sira-geo-field-label", htmlFor="geo-municipio"),
                dcc.Dropdown(
                    id="geo-municipio",
                    options=muni_opts,
                    value=muni_id or None,
                    placeholder="Municipio",
                    clearable=False,
                    className="sira-geo-select",
                ),
            ]),
            html.Div(className="sira-geo-field", children=[
                html.Label("Localidad", className="sira-geo-field-label", htmlFor="geo-localidad"),
                dcc.Dropdown(
                    id="geo-localidad",
                    options=loc_opts,
                    value=loc_id or None,
                    placeholder="Localidad",
                    clearable=False,
                    className="sira-geo-select",
                ),
            ]),
        ]),
    ])
