"""Componentes reutilizables del layout Dash."""
from __future__ import annotations

from dash import dcc, html

from theme import C_CYAN, C_GREEN, C_MUTED, C_ORANGE, C_TEAL, COLORES


def nivel_etiqueta(nivel: str | None) -> str:
    if not nivel or nivel == "—":
        return "—"
    return {
        "MÍNIMO": "Mínimo",
        "BAJO": "Bajo",
        "MODERADO": "Moderado",
        "ALTO": "Alto",
        "CRÍTICO": "Crítico",
    }.get(nivel, nivel.title())


def mag_con_riesgo(mag: float, nivel: str | None) -> html.Div:
    color = COLORES.get(nivel or "", C_MUTED)
    return html.Div(className="sira-mag-riesgo", children=[
        html.Span(f"{mag:.1f}", className="sira-card-value-num"),
        html.Span(className="sira-riesgo-badge", children=[
            html.Span("Riesgo: ", className="sira-riesgo-label"),
            html.Span(nivel_etiqueta(nivel), className="sira-riesgo-val", style={"color": color}),
        ]),
    ])


def card(titulo, valor, detalle, ayuda, accent: str = C_CYAN) -> html.Div:
    return html.Div(
        className="sira-card",
        style={"borderLeftColor": accent},
        children=[
            html.Div(titulo, className="sira-card-title"),
            html.Div(valor, className="sira-card-value") if isinstance(valor, str) else valor,
            html.Div(detalle, className="sira-card-detail") if isinstance(detalle, str) else detalle,
            html.P(ayuda, className="sira-card-help"),
        ],
    )


def regiones(reg: dict) -> html.Div:
    items = [
        ("Mediterráneo", reg.get("MEDITERRÁNEO", 0), C_ORANGE),
        ("Cantábrico", reg.get("CANTÁBRICO", 0), C_GREEN),
        ("Atlántico", reg.get("ATLÁNTICO", 0), C_CYAN),
    ]
    return html.Div(className="sira-regiones", children=[
        html.Div([
            html.Span(nombre, style={"color": color, "fontWeight": "600"}),
            html.Span(f": {valor}", className="sira-region-val"),
        ]) for nombre, valor, color in items
    ])


def bloque(gid: str, titulo: str, ayuda: str | None = None, *, full: bool = False, accent: str = C_CYAN) -> html.Div:
    clases = "sira-bloque sira-bloque--full" if full else "sira-bloque"
    graph_wrap = "sira-graph-wrap sira-graph-wrap--map" if full else "sira-graph-wrap"
    children: list = [html.H4(titulo, className="sira-bloque-title")]
    if ayuda:
        children.append(html.P(ayuda, className="sira-bloque-help"))
    children.append(html.Div(className=graph_wrap, children=[
        dcc.Graph(
            id=gid,
            config={"displayModeBar": False, "responsive": True},
            style={"height": "100%", "width": "100%"},
        ),
    ]))
    return html.Div(className=clases, style={"borderTopColor": accent}, children=children)


def dir_compass(grados) -> str:
    if grados is None or grados == "—":
        return "—"
    g = float(grados) % 360
    puntos = ("N", "NE", "E", "SE", "S", "SO", "O", "NO")
    cardinal = puntos[int((g + 22.5) / 45) % 8]
    return f"{g:.0f}° ({cardinal})"
