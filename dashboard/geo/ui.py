"""Selector geográfico España (provincia → municipio → localidad)."""
from __future__ import annotations

from dash import dcc, html

from sira.infrastructure.geo.es import localidades, municipios, opciones, provincias


def _dropdown(drop_id: str, opts: list, value: str | None, placeholder: str) -> html.Div:
    return html.Div(className="sira-geo-select-wrap", children=[
        dcc.Dropdown(
            id=drop_id,
            options=opts,
            value=value or None,
            placeholder=placeholder,
            clearable=False,
            searchable=drop_id != "geo-localidad",
        ),
    ])


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
        html.Button("Usar mi ubicación", id="geo-locate-btn", n_clicks=0, className="sira-btn-geo"),
        html.Div(className="sira-geo-fields", children=[
            html.Div(className="sira-geo-field", children=[
                html.Label("Provincia", className="sira-geo-field-label", htmlFor="geo-provincia"),
                _dropdown("geo-provincia", prov_opts, prov_id, "Provincia"),
            ]),
            html.Div(className="sira-geo-field", children=[
                html.Label("Municipio", className="sira-geo-field-label", htmlFor="geo-municipio"),
                _dropdown("geo-municipio", muni_opts, muni_id, "Municipio"),
            ]),
            html.Div(className="sira-geo-field", children=[
                html.Label("Localidad", className="sira-geo-field-label", htmlFor="geo-localidad"),
                _dropdown("geo-localidad", loc_opts, loc_id, "Localidad"),
            ]),
        ]),
    ])
