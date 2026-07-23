"""Componentes reutilizables del layout Dash."""
from __future__ import annotations

from dash import dcc, html
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from ui.theme import C_CYAN, C_GREEN, C_MUTED, C_ORANGE, C_TEAL, COLORES

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


def card_lluvia(
    valor,
    detalle: str,
    ayuda: str,
    *,
    accent: str = C_TEAL,
    tooltip: str | None = None,
) -> html.Div:
    """Tarjeta Lluvia 24h con previsión horaria integrada."""
    children: list = [
        html.Div("Lluvia 24h", className="sira-card-title"),
        html.Div(valor, className="sira-card-value") if isinstance(valor, str) else valor,
    ]
    if detalle:
        children.append(html.Div(detalle, className="sira-card-detail"))
    children.append(html.Div(className="sira-card-lluvia-chart", children=[
        dcc.Graph(
            id="lluvia",
            config={"displayModeBar": False, "responsive": True},
            style={"height": "100%", "width": "100%"},
        ),
    ]))
    if ayuda:
        children.append(html.P(ayuda, className="sira-card-help"))
    return html.Div(
        className="sira-card sira-card--lluvia",
        style={"borderLeftColor": accent},
        title=tooltip,
        children=children,
    )


def card(titulo, valor, detalle, ayuda, accent: str = C_CYAN, tooltip: str | None = None) -> html.Div:
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
    return html.Div(
        className="sira-card",
        style={"borderLeftColor": accent},
        title=tooltip,
        children=children,
    )


def card_doble(
    titulo: str,
    valor_esp: int | str,
    etiqueta_esp: str,
    valor_loc: int | str,
    etiqueta_loc: str,
    ayuda: str,
    accent: str = C_CYAN,
    tooltip: str | None = None,
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
    return card(titulo, valor, "", ayuda, accent, tooltip=tooltip)


def card_sismos_combinada(
    n_esp: int,
    n_loc: int,
    localidad: str,
    mag_max: float,
    nivel_max: str | None,
    detalle: str,
    ayuda: str,
    accent: str = C_ORANGE,
    tooltip: str | None = None,
) -> html.Div:
    valor = html.Div(className="sira-card-sismos-combo", children=[
        html.Div(className="sira-card-dual", children=[
            html.Div(
                className="sira-card-dual-part",
                title=tooltip,
                children=[
                    html.Span(str(n_esp), className="sira-card-value-num"),
                    html.Span("España", className="sira-card-dual-lbl"),
                ],
            ),
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
    return card("Sismos", valor, "", ayuda, accent, tooltip=tooltip)


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
    motivo = str(elem.get("motivo") or "").strip()
    return html.Div(className="sira-riesgo-elem", title=motivo or None, children=cuerpo)


def riesgo_meteo_panel(riesgo: dict) -> html.Div:
    horas = riesgo.get("horas", 48)
    elementos = riesgo.get("elementos") or riesgo.get("fenomenos") or []
    indice = riesgo.get("indice_global", riesgo.get("indice", 0))
    nivel = riesgo.get("nivel_global", riesgo.get("nivel", "MÍNIMO"))
    color_global = COLORES.get(nivel, C_MUTED)
    motivo_indice = str(riesgo.get("motivo_indice") or "").strip()

    filas: list = [html.Div(f"Horizonte: próximas {horas} h", className="sira-riesgo-meteo-horas")]

    if not elementos:
        filas.append(html.Div("Sin fenómenos adversos destacados", className="sira-riesgo-vacio"))
    else:
        item_nodes = [_riesgo_elemento(elem) for elem in elementos]
        scroll_cls = "sira-riesgo-scroll sira-riesgo-scroll--multi"
        filas.append(html.Div(item_nodes, className=scroll_cls))

    filas.append(
        html.Div(
            className="sira-riesgo-global",
            title=motivo_indice or None,
            children=[
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
            ],
        )
    )
    return html.Div(className="sira-riesgo-meteo", children=filas)


def impacto_local_panel(riesgo: dict) -> html.Div:
    """Índice compuesto 0–100 % con barras por eje."""
    indice = int(riesgo.get("indice") or 0)
    nivel = str(riesgo.get("nivel") or "MÍNIMO")
    color = COLORES.get(nivel, C_MUTED)
    ejes = riesgo.get("ejes") or []

    filas: list = [
        html.Div(className="sira-impacto-header", children=[
            html.Span(f"{indice}", className="sira-impacto-valor", style={"color": color}),
            html.Span("%", className="sira-impacto-unidad"),
            html.Span(nivel_etiqueta(nivel), className="sira-impacto-nivel", style={"color": color}),
        ]),
    ]
    if riesgo.get("concurrencia"):
        filas.append(html.Div("Varias amenazas simultáneas", className="sira-impacto-concurrencia"))

    for eje in ejes:
        pct = int(eje.get("pct") or 0)
        if pct <= 0:
            continue
        motivo = str(eje.get("motivo") or "").strip()
        filas.append(html.Div(
            className="sira-impacto-eje",
            title=motivo or None,
            children=[
                html.Div(className="sira-impacto-eje-top", children=[
                    html.Span(eje.get("nombre") or "—", className="sira-impacto-eje-nom"),
                    html.Span(f"{pct}%", className="sira-impacto-eje-pct"),
                ]),
                html.Div(className="sira-impacto-bar", children=[
                    html.Div(
                        className="sira-impacto-bar-fill",
                        style={"width": f"{pct}%", "backgroundColor": color if pct >= 60 else C_TEAL},
                    ),
                ]),
            ],
        ))

    filas.append(html.Div(
        "Índice orientativo según señales activas. No sustituye avisos oficiales.",
        className="sira-impacto-nota",
    ))
    return html.Div(className="sira-impacto-local", children=filas)


def card_impacto_local(riesgo: dict) -> html.Div:
    nivel = str(riesgo.get("nivel") or "MÍNIMO")
    accent = COLORES.get(nivel, C_ORANGE)
    h = riesgo.get("horas_meteo", 48)
    return card(
        "Impacto grave local",
        impacto_local_panel(riesgo),
        riesgo.get("texto") or "",
        f"Combinación ponderada de meteo, hidrología, sismos, incendios y calor ({h} h).",
        accent=accent,
        tooltip="Índice compuesto local (0-100). Prioriza señales concurrentes en meteo, hidrología, sismos, incendios y calor.",
    )


def _zona_alerta_corta(area_desc: str | None) -> str:
    """«Litoral sur de Valencia-Valencia/Valencia» → «Litoral sur de Valencia»."""
    txt = str(area_desc or "").strip()
    if "-" in txt:
        txt = txt.split("-", 1)[0].strip()
    return txt or "Zona AEMET"


def _detalle_alerta_tiempo(alerta: dict, fmt_detalle) -> tuple[str, str]:
    """(detalle corto, texto adicional) a partir del aviso CAP."""
    full = str(fmt_detalle(alerta) or "").strip()
    if not full:
        return "", ""
    if ". " in full:
        corto, extra = full.split(". ", 1)
        return corto.strip(), extra.strip()
    return full, ""


def _agrupar_resumen_alertas_tiempo(
    alertas: list[dict] | None,
    timestamps: list[str],
    *,
    parse_dt,
    nivel_rank,
    fmt_detalle,
) -> list[tuple[str, str, str]]:
    """Agrupa avisos térmicos: una línea por nivel+detalle, zonas unidas."""
    if not alertas:
        return []

    def _vigente_en_serie(alerta: dict) -> bool:
        if not timestamps:
            return True
        ini = parse_dt(alerta.get("onset"))
        fin = parse_dt(alerta.get("expires"))
        for ts in timestamps:
            t = parse_dt(ts)
            if t is None:
                continue
            if ini and t < ini:
                continue
            if fin and t > fin:
                continue
            return True
        return False

    grupos: dict[tuple[str, str, str], list[str]] = {}
    for alerta in alertas:
        if str(alerta.get("fenomeno") or "").upper() not in {"AT", "BT"}:
            continue
        if not _vigente_en_serie(alerta):
            continue
        nivel = str(alerta.get("level") or "").lower()
        corto, extra = _detalle_alerta_tiempo(alerta, fmt_detalle)
        if not corto:
            continue
        zona = _zona_alerta_corta(alerta.get("area_desc"))
        key = (nivel, corto, extra)
        bucket = grupos.setdefault(key, [])
        if zona not in bucket:
            bucket.append(zona)

    lineas: list[tuple[str, str, str]] = []
    for (nivel, corto, extra), zonas in grupos.items():
        zonas_txt = ", ".join(sorted(zonas, key=str.lower))
        lineas.append((nivel, zonas_txt, corto if not extra else f"{corto}. {extra}"))

    lineas.sort(key=lambda row: (-nivel_rank(row[0]), row[1].lower()))
    return lineas


def meteo_ahora(
    resumen: dict,
    proximas_horas: list[dict] | None = None,
    *,
    fuente: str | None = None,
    alertas: list[dict] | None = None,
    horas: int = 6,
) -> html.Div:
    from sira.infrastructure.sources.meteo.aemet_alerts import fmt_alerta_detalle

    _MADRID = ZoneInfo("Europe/Madrid")

    def _parse_dt(value: str | None):
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_MADRID)
        return dt.astimezone(timezone.utc)

    def _nivel_rank(level: str | None) -> int:
        return {"amarillo": 1, "naranja": 2, "rojo": 3}.get(str(level or "").lower(), 0)

    def _temp_alerta(ts: str) -> dict | None:
        objetivo = _parse_dt(ts)
        if objetivo is None:
            return None
        mejor = None
        mejor_rank = 0
        for alerta in alertas or []:
            if str(alerta.get("fenomeno") or "").upper() not in {"AT", "BT"}:
                continue
            ini = _parse_dt(alerta.get("onset"))
            fin = _parse_dt(alerta.get("expires"))
            if ini and objetivo < ini:
                continue
            if fin and objetivo > fin:
                continue
            rank = _nivel_rank(alerta.get("level"))
            if rank > mejor_rank:
                mejor = alerta
                mejor_rank = rank
        return mejor

    def _bg_alerta(level: str | None) -> dict:
        lv = str(level or "").lower()
        if lv == "rojo":
            return {
                "background": "rgba(239, 68, 68, 0.24)",
                "borderColor": "rgba(248, 113, 113, 0.65)",
            }
        if lv == "naranja":
            return {
                "background": "rgba(249, 115, 22, 0.22)",
                "borderColor": "rgba(251, 146, 60, 0.65)",
            }
        if lv == "amarillo":
            return {
                "background": "rgba(250, 204, 21, 0.22)",
                "borderColor": "rgba(250, 204, 21, 0.62)",
            }
        return {}

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

    # Predicción de temperatura para próximas horas (AEMET / Open-Meteo).
    next_nodes: list = []
    serie_ok = [r for r in (proximas_horas or []) if isinstance(r, dict) and r.get("timestamp")]
    serie_ok = serie_ok[:max(1, int(horas))]
    if serie_ok:
        item_nodes: list = []
        for i, row in enumerate(serie_ok):
            ts = str(row.get("timestamp") or "")
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                hora_txt = dt.strftime("%H:%M")
            except ValueError:
                hora_txt = "—"

            temp_n = row.get("temp_c")
            sens_n = row.get("sensacion_c")
            try:
                temp_txt = f"{float(temp_n):.1f}°"
            except (TypeError, ValueError):
                temp_txt = "—"
            try:
                sens_txt_h = f"{float(sens_n):.1f}°"
            except (TypeError, ValueError):
                sens_txt_h = "—"
            alerta_h = _temp_alerta(ts)
            item_style = _bg_alerta((alerta_h or {}).get("level"))
            item_nodes.append(
                html.Div(
                    children=[
                        html.Div(hora_txt, className="sira-meteo-next-h"),
                        html.Div(temp_txt, className="sira-meteo-next-temp"),
                        html.Div(f"Sens. {sens_txt_h}", className="sira-meteo-next-sens"),
                    ],
                    className="sira-meteo-next-item",
                    style=item_style,
                )
            )

        resumen_alertas: list = []
        timestamps = [str(r.get("timestamp") or "") for r in serie_ok if r.get("timestamp")]
        for nivel, zonas_txt, detalle in _agrupar_resumen_alertas_tiempo(
            alertas,
            timestamps,
            parse_dt=_parse_dt,
            nivel_rank=_nivel_rank,
            fmt_detalle=fmt_alerta_detalle,
        ):
            resumen_alertas.append(
                html.Div(
                    f"{nivel.upper()} · {zonas_txt} · {detalle}",
                    className="sira-meteo-alerta-linea",
                )
            )

        next_nodes = [
            html.Div(
                f"Próx. horas — {str(fuente or '—').strip()} (temperatura)",
                className="sira-meteo-next-title",
            ),
            html.Div(item_nodes, className="sira-meteo-next-grid"),
            html.Div(resumen_alertas, className="sira-meteo-alertas-list") if resumen_alertas else None,
        ]
    return html.Div(
        className="sira-meteo-ahora",
        children=[
            html.Span(icon, className="sira-meteo-icon", title=estado),
            html.Div(className="sira-meteo-body", children=cuerpo + next_nodes),
        ],
    )
