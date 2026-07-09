"""Componentes reutilizables del layout Dash."""
from __future__ import annotations

from dash import dcc, html

from theme import C_CYAN, C_GREEN, C_MUTED, C_ORANGE, C_TEAL, COLORES

_PELIGRO_COLOR = {
    "rojo": "#ef4444",
    "naranja": C_ORANGE,
    "amarillo": "#eab308",
}


def nivel_etiqueta(nivel: str | None) -> str:
    if not nivel or nivel == "—":
        return "—"
    return {
        "MÍNIMO": "Mínimo",
        "BAJO": "Bajo",
        "MODERADO": "Moderado",
        "ALTO": "Alto",
        "MUY ALTO": "Muy alto",
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


def lluvia_embalses_valor(
    precip_mm: float | int | str,
    resumen_emb: dict,
    resumen_afor: dict | None = None,
) -> html.Div:
    """Bloque principal de la tarjeta Lluvia 24h con líneas de embalses y aforos."""
    n_emb = int(resumen_emb.get("n_alertas_local") or 0)
    linea_emb = str(resumen_emb.get("texto_linea") or "")
    filas = [html.Div(f"{precip_mm} mm", className="sira-card-value-num")]
    if linea_emb:
        filas.append(html.Div(
            linea_emb,
            className="sira-card-detail sira-embalses-linea",
            style={"color": "#38bdf8" if n_emb else None},
        ))
    if resumen_afor:
        n_afor = int(resumen_afor.get("n_alertas_local") or 0)
        linea_afor = str(resumen_afor.get("texto_linea") or "")
        if linea_afor:
            tiene_sensor_caido = any(
                a.get("sin_datos_recientes") for a in (resumen_afor.get("principales") or [])
            )
            filas.append(html.Div(
                linea_afor,
                className="sira-card-detail sira-aforos-linea"
                + (" sira-aforos-linea--sensor" if tiene_sensor_caido else ""),
                style={"color": "#f59e0b" if tiene_sensor_caido else ("#14b8a6" if n_afor else None)},
            ))
    return html.Div(className="sira-lluvia-embalses", children=filas)


def card(titulo, valor, detalle, ayuda, accent: str = C_CYAN) -> html.Div:
    children: list = [
        html.Div(titulo, className="sira-card-title"),
        html.Div(valor, className="sira-card-value") if isinstance(valor, str) else valor,
    ]
    if isinstance(detalle, str) and detalle:
        children.append(html.Div(detalle, className="sira-card-detail"))
    elif detalle is not None and not isinstance(detalle, str):
        children.append(detalle)
    if ayuda:
        children.append(html.P(ayuda, className="sira-card-help"))
    return html.Div(className="sira-card", style={"borderLeftColor": accent}, children=children)


def card_doble(
    titulo: str,
    valor_esp: int | str,
    etiqueta_esp: str,
    valor_loc: int | str,
    etiqueta_loc: str,
    ayuda: str,
    accent: str = C_CYAN,
) -> html.Div:
    """Tarjeta con dos cifras: España / localidad."""
    valor = html.Div(className="sira-card-dual", children=[
        html.Div(className="sira-card-dual-part", children=[
            html.Span(str(valor_esp), className="sira-card-value-num"),
            html.Span(etiqueta_esp, className="sira-card-dual-lbl"),
        ]),
        html.Span("·", className="sira-card-dual-sep"),
        html.Div(className="sira-card-dual-part", children=[
            html.Span(str(valor_loc), className="sira-card-value-num"),
            html.Span(etiqueta_loc, className="sira-card-dual-lbl"),
        ]),
    ])
    return card(titulo, valor, "", ayuda, accent)


def card_sismos_combinada(
    n_esp: int,
    n_loc: int,
    localidad: str,
    mag_max: float,
    nivel_max: str | None,
    detalle: str,
    ayuda: str,
    accent: str = C_ORANGE,
) -> html.Div:
    valor = html.Div(className="sira-card-sismos-combo", children=[
        html.Div(className="sira-card-dual", children=[
            html.Div(className="sira-card-dual-part", children=[
                html.Span(str(n_esp), className="sira-card-value-num"),
                html.Span("España", className="sira-card-dual-lbl"),
            ]),
            html.Span("·", className="sira-card-dual-sep"),
            html.Div(className="sira-card-dual-part", children=[
                html.Span(str(n_loc), className="sira-card-value-num"),
                html.Span(f"perceptibles · {localidad}", className="sira-card-dual-lbl"),
            ]),
        ]),
        html.Div(className="sira-card-sismos-mag", children=[
            mag_con_riesgo(mag_max, nivel_max),
            html.Div(detalle, className="sira-card-detail") if detalle else None,
        ]),
    ])
    return card("Sismos", valor, "", ayuda, accent)


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


def bloque(
    gid: str,
    titulo: str,
    ayuda: str | None = None,
    *,
    map_chart: bool = False,
    accent: str = C_CYAN,
) -> html.Div:
    graph_wrap = "sira-graph-wrap sira-graph-wrap--map" if map_chart else "sira-graph-wrap"
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
    return html.Div(className="sira-bloque", style={"borderTopColor": accent}, children=children)


def dir_compass(grados) -> str:
    if grados is None or grados == "—":
        return "—"
    g = float(grados) % 360
    puntos = ("N", "NE", "E", "SE", "S", "SO", "O", "NO")
    cardinal = puntos[int((g + 22.5) / 45) % 8]
    return f"{g:.0f}° ({cardinal})"


def _riesgo_elemento(elem: dict) -> html.Div:
    nivel_key = str(elem.get("nivel_peligro") or "").lower()
    peligro_color = _PELIGRO_COLOR.get(nivel_key, C_MUTED)
    secundario = [
        html.Span(
            elem.get("nivel_label") or "—",
            className="sira-riesgo-peligro-badge",
            style={"borderColor": peligro_color, "color": peligro_color},
        ),
        html.Span(elem.get("nivel_etiqueta") or "Nivel de peligro", className="sira-riesgo-peligro-lbl"),
    ]
    cuerpo: list = [
        html.Div(className="sira-riesgo-elem-top", children=[
            html.Span(elem.get("icon") or "⚠️", className="sira-meteo-icon"),
            html.Span(elem.get("desc") or "—", className="sira-riesgo-elem-nombre"),
        ]),
        html.Div(className="sira-riesgo-elem-principal", children=[
            html.Span(elem.get("prob_principal") or "—", className="sira-riesgo-prob-val"),
            html.Span(elem.get("prob_etiqueta") or "Probabilidad AEMET", className="sira-riesgo-prob-lbl"),
        ]),
    ]
    if elem.get("parametro"):
        cuerpo.append(html.Div(elem["parametro"], className="sira-riesgo-elem-param"))
    if elem.get("tiempo_actual"):
        cuerpo.append(html.Div(elem["tiempo_actual"], className="sira-riesgo-elem-ahora"))
    area = elem.get("area")
    if area:
        cuerpo.append(html.Div(area, className="sira-riesgo-elem-zona"))
    cuerpo.append(html.Div(className="sira-riesgo-elem-secundario", children=secundario))
    return html.Div(className="sira-riesgo-elem", children=cuerpo)


def riesgo_meteo_panel(riesgo: dict) -> html.Div:
    horas = riesgo.get("horas", 48)
    elementos = riesgo.get("elementos") or riesgo.get("fenomenos") or []
    indice = riesgo.get("indice_global", riesgo.get("indice", 0))
    nivel = riesgo.get("nivel_global", riesgo.get("nivel", "MÍNIMO"))
    color_global = COLORES.get(nivel, C_MUTED)

    filas: list = [html.Div(f"Horizonte: próximas {horas} h", className="sira-riesgo-meteo-horas")]

    if not elementos:
        filas.append(html.Div("Sin fenómenos adversos destacados", className="sira-riesgo-vacio"))
    else:
        item_nodes = [_riesgo_elemento(elem) for elem in elementos]
        scroll_cls = "sira-riesgo-scroll sira-riesgo-scroll--multi"
        filas.append(html.Div(item_nodes, className=scroll_cls))

    filas.append(
        html.Div(className="sira-riesgo-global", children=[
            html.Span("Índice combinado (opcional)", className="sira-riesgo-global-lbl"),
            html.Span(
                f"{indice}/100 · {nivel_etiqueta(nivel)}",
                className="sira-riesgo-global-val",
                style={"color": color_global},
            ),
            html.Span(
                "Índice orientativo.",
                className="sira-riesgo-global-nota",
            ),
        ])
    )
    return html.Div(className="sira-riesgo-meteo", children=filas)


def meteo_ahora(resumen: dict) -> html.Div:
    icon = resumen.get("tiempo_icon") or "🌡️"
    estado = resumen.get("tiempo_texto") or "—"
    temp = resumen.get("temp_c")
    sens = resumen.get("sensacion_c")
    hum = resumen.get("humedad_pct")
    vel = resumen.get("viento_vel")
    unidad = resumen.get("viento_unidad") or "m/s"
    dir_txt = resumen.get("viento_dir_texto")
    if not dir_txt and resumen.get("viento_dir_grados") is not None:
        dir_txt = dir_compass(resumen.get("viento_dir_grados"))
    vel_ms = None
    if vel is not None:
        try:
            vel_ms = float(vel)
            if str(unidad).lower().startswith("km"):
                vel_ms = vel_ms / 3.6
        except (TypeError, ValueError):
            vel_ms = None
    dir_card = None
    if dir_txt:
        txt = str(dir_txt).strip()
        if "(" in txt and ")" in txt:
            dir_card = txt.split("(", 1)[1].split(")", 1)[0].strip()
        elif txt:
            dir_card = txt

    sens_txt = f"{float(sens):.1f}" if sens is not None else "—"
    hum_txt = f"{int(hum)}" if hum is not None else "—"
    if vel_ms is None:
        viento_txt = "Viento: —"
    else:
        v_txt = f"{vel_ms:.1f}"
        viento_txt = f"Viento: {v_txt} m/s"
        if dir_card:
            viento_txt += f" ({dir_card})"

    cuerpo: list = [
        html.Div(estado, className="sira-meteo-estado"),
        html.Div(
            f"{temp} °C" if temp is not None else "—",
            className="sira-meteo-temp",
        ),
        html.Div(f"Sensación térmica: {sens_txt}ºC", className="sira-meteo-extra"),
        html.Div(f"Humedad relativa: {hum_txt}%", className="sira-meteo-extra"),
        html.Div(viento_txt, className="sira-meteo-viento"),
    ]
    return html.Div(className="sira-meteo-ahora", children=[
        html.Span(icon, className="sira-meteo-icon", title=estado),
        html.Div(className="sira-meteo-body", children=cuerpo),
    ])
