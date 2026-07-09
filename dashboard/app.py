"""Dashboard SIRA."""
from __future__ import annotations

import _bootstrap  # noqa: F401

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import requests
from dash import Dash, Input, Output, State, callback, clientside_callback, ctx, dcc, html
from flask import jsonify, send_from_directory
from dash.exceptions import PreventUpdate

from components import bloque, card, card_doble, card_sismos_combinada, dir_compass, lluvia_embalses_valor, mag_con_riesgo, meteo_ahora, riesgo_meteo_panel
from config import (  # noqa: E402
    AEMET_MUNICIPIO,
    ALLOW_DATA_REFRESH,
    API_BASE_URL,
    API_KEY,
    COSTERO_MAP_MAX,
    DASHBOARD_HOST,
    DASHBOARD_PORT,
    DASHBOARD_REFRESH_MS,
    DASHBOARD_REFRESH_MIN,
    DATA_FILE,
    AFORO_MAP_MAX,
    AFORO_RADIO_LOCAL_KM,
    EMBALSE_MAP_MAX,
    EMBALSE_RADIO_LOCAL_KM,
    FORECAST_DAYS,
    INCENDIO_MAP_MAX,
    INCENDIO_RADIO_LOCAL_KM,
    INGESTA_INTERVAL_MIN,
    MAP_CIRCLE_POINTS,
    MARES,
    MAPA,
    RIESGO_METEO_HORAS,
    ZONA,
)
from db import count_subscriptions, get_historial_municipio
from core import fmt_ingesta_local, read_dashboard  # noqa: E402
from geo_ccaa_mapa import anadir_bordes_ccaa, anadir_bordes_provincias, anadir_costa_ign
from geo_es import (
    coords_observacion,
    localidades,
    municipio_por_id,
    municipios,
    opciones,
    provincia_de_municipio,
    provincias,
    viewport_ccaa,
    viewport_ccaa_centro,
    viewport_fit_contenedor,
    viewport_fit_observacion,
    projection_scale_for_viewport,
)
from geo_ui import selector_geo
from meteo_live import meteo_localidad
from aemet_alerts import alerta_coincide_zona, alerta_firma, deduplicar_alertas
from costa_mapa import alertas_a_capa_costera
from sismos import circle_disk_polygon, circle_perimeter, enriquecer_local
from incendios import enriquecer_local as enriquecer_incendio_local
from hidrologia import embalses_para_mapa, resumen_embalses
from aforos import aforos_para_mapa, resumen_aforos
from tsunami_oficial import anexar_boletin_tsunami
from riesgo_meteo import calcular_riesgo_meteo
from theme import (
    C_CYAN,
    C_GREEN,
    C_MUTED,
    C_NAVY,
    C_ORANGE,
    C_TEAL,
    C_TEXT,
    COLORES,
    PLOTLY_BG,
)

SEMAFORO_COLORES = {
    "VERDE": "#22c55e",
    "AMARILLO": "#eab308",
    "NARANJA": "#f97316",
    "ROJO": "#ef4444",
}

_ASSETS = Path(__file__).resolve().parent / "assets"
_LOGO_FILE = _ASSETS / "logo-sira_4.png"
if not _LOGO_FILE.is_file():
    raise SystemExit(f"Falta el logo: {_LOGO_FILE}")

app = Dash(
    __name__,
    title="SIRA — Sistema Ibérico de Riesgos y Alerta",
    assets_folder=str(_ASSETS),
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)

app.index_string = """
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <link rel="stylesheet" href="/assets/sira.css?v=32">
        <link rel="icon" href="/assets/logo-sira_4.png?v=8" type="image/png">
        <link rel="manifest" href="/manifest.webmanifest">
        <script src="/assets/geo.js"></script>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
"""

_LOGO = app.get_asset_url("logo-sira_4.png") + "?v=8"

_DEFAULT_MUNI = str(AEMET_MUNICIPIO).zfill(5)
_DEFAULT_PROV = provincia_de_municipio(_DEFAULT_MUNI) or "46"
_locs = localidades(_DEFAULT_MUNI)
_DEFAULT_LOC = _locs[0]["id"] if _locs else _DEFAULT_MUNI

_AYUDA_OCE_PREVISION = f"Previsión horaria · {FORECAST_DAYS} días · Open-Meteo Marine"


def _default_geo() -> dict:
    muni = municipio_por_id(_DEFAULT_MUNI)
    prov = next((p for p in provincias() if p["id"] == _DEFAULT_PROV), None)
    loc = _locs[0] if _locs else None
    lat_obs, lon_obs, _ = coords_observacion(_DEFAULT_MUNI, loc["id"] if loc else None)
    return {
        "provincia_id": _DEFAULT_PROV,
        "provincia": prov["nombre"] if prov else None,
        "municipio_id": _DEFAULT_MUNI,
        "municipio": muni["nombre"] if muni else None,
        "localidad_id": loc["id"] if loc else None,
        "localidad": loc["nombre"] if loc else None,
        "map_zoom": viewport_ccaa_centro(_DEFAULT_PROV, lat_obs, lon_obs, alejado=True),
    }


def _geo_resuelto(geo: dict | None) -> dict:
    """Geo efectiva del panel: nombres siempre coherentes con los IDs."""
    if not geo:
        return _default_geo()

    muni_id = str(geo.get("municipio_id") or _DEFAULT_MUNI).zfill(5)
    muni = municipio_por_id(muni_id)
    pid = str(geo.get("provincia_id") or provincia_de_municipio(muni_id) or _DEFAULT_PROV).zfill(2)
    prov = next((p for p in provincias() if p["id"] == pid), None)
    locs = localidades(muni_id)
    loc_id = geo.get("localidad_id")
    loc = next((l for l in locs if l["id"] == loc_id), locs[0] if locs else None)

    out = {
        "provincia_id": pid,
        "provincia": prov["nombre"] if prov else geo.get("provincia"),
        "municipio_id": muni_id,
        "municipio": muni["nombre"] if muni else geo.get("municipio"),
        "localidad_id": loc["id"] if loc else geo.get("localidad_id"),
        "localidad": loc["nombre"] if loc else geo.get("localidad"),
    }
    zoom = geo.get("map_zoom")
    if zoom:
        out["map_zoom"] = zoom
    else:
        lat_obs, lon_obs, _ = coords_observacion(muni_id, out.get("localidad_id"))
        out["map_zoom"] = viewport_ccaa_centro(pid, lat_obs, lon_obs, alejado=True)
    return out

_BTN_CLASS = "sira-btn-refresh" + ("" if ALLOW_DATA_REFRESH else " sira-btn-refresh--hidden")

app.layout = html.Div(className="sira-page", children=[
    dcc.Location(id="url", refresh=False),
    html.Div(id="sira-meta", **{"data-api-base": API_BASE_URL}, style={"display": "none"}),
    html.Div(id="push-geo", style={"display": "none"}),
    html.Header(className="sira-header", children=[
        html.Div(className="sira-header-inner", children=[
            html.Div(className="sira-header-text", children=[
                html.H1("SIRA", className="sira-title"),
                html.P("Sistema Ibérico de Riesgos y Alerta", className="sira-subtitle"),
            ]),
            html.Img(
                src=_LOGO,
                className="sira-logo",
                alt="SIRA — Sistema Ibérico de Riesgos y Alerta",
            ),
        ]),
    ]),
    html.Main(className="sira-main", children=[
        html.Div(className="sira-container", children=[
            dcc.Interval(id="tick", interval=DASHBOARD_REFRESH_MS, n_intervals=0),
            dcc.Store(id="data-ts-store"),
            dcc.Store(id="geo-store", data=_default_geo()),
            dcc.Interval(id="geo-locate-poll", interval=500, n_intervals=0, disabled=True, max_intervals=60),
            html.Div(id="geo-locate-pending", style={"display": "none"}),
            selector_geo(_DEFAULT_PROV, _DEFAULT_MUNI, _DEFAULT_LOC),
            html.Div(id="page-home", children=[
                html.Div(className="sira-toolbar", children=[
                    html.Div(className="sira-ts-wrap", children=[
                        html.Span("Última ingesta: ", className="sira-ts-label"),
                        html.Span(id="ts", className="sira-ts"),
                        html.Span("Hora local", className="sira-ts-badge"),
                        html.Span(
                            f" · pantalla cada {DASHBOARD_REFRESH_MIN} min · datos cada {INGESTA_INTERVAL_MIN} min",
                            className="sira-ts-hint",
                        ),
                    ]),
                    html.Div(className="sira-toolbar-actions", children=[
                        html.A("Historial 30 días", href="/historial", className="sira-link-nav"),
                        html.A("Estado", href="/status", className="sira-link-nav"),
                        html.Button("Actualizar", id="btn", n_clicks=0, className=_BTN_CLASS),
                        html.Button("Activar notificaciones", id="push-btn", n_clicks=0, className="sira-btn-push"),
                        html.Span("Push: desactivado", id="push-status", className="sira-push-status"),
                    ]),
                ]),
                html.Div(id="cards", className="sira-cards"),
                html.Div(className="sira-charts", children=[
                html.Div(className="sira-charts-row sira-charts-row--map-lluvia", children=[
                    bloque(
                        "mapa", "Mapa de riesgos — España",
                        None,
                        map_chart=True, accent=C_ORANGE,
                    ),
                    bloque(
                        "lluvia", "Previsión de lluvia",
                        "Según la localidad seleccionada · AEMET o Open-Meteo · embalses y aforos SAIH.",
                        accent=C_TEAL,
                    ),
                ]),
                html.Div(className="sira-charts-row sira-charts-row--3", children=[
                    bloque(
                        "sst_med", "Previsión SST — Mediterráneo",
                        f"{_AYUDA_OCE_PREVISION} · {MARES['MEDITERRÁNEO']['punto']}.",
                        accent=C_ORANGE,
                    ),
                    bloque(
                        "sst_cant", "Previsión SST — Cantábrico",
                        f"{_AYUDA_OCE_PREVISION} · {MARES['CANTÁBRICO']['punto']}.",
                        accent=C_GREEN,
                    ),
                    bloque(
                        "sst_atl", "Previsión SST — Atlántico",
                        f"{_AYUDA_OCE_PREVISION} · {MARES['ATLÁNTICO']['punto']}.",
                        accent=C_CYAN,
                    ),
                ]),
                html.Div(className="sira-charts-row sira-charts-row--3", children=[
                    bloque(
                        "cor_med", "Previsión corrientes — Mediterráneo",
                        f"{_AYUDA_OCE_PREVISION} · {MARES['MEDITERRÁNEO']['punto']}.",
                        accent=C_ORANGE,
                    ),
                    bloque(
                        "cor_cant", "Previsión corrientes — Cantábrico",
                        f"{_AYUDA_OCE_PREVISION} · {MARES['CANTÁBRICO']['punto']}.",
                        accent=C_GREEN,
                    ),
                    bloque(
                        "cor_atl", "Previsión corrientes — Atlántico",
                        f"{_AYUDA_OCE_PREVISION} · {MARES['ATLÁNTICO']['punto']}.",
                        accent=C_CYAN,
                    ),
                ]),
            ]),
            ]),
            html.Div(id="page-historial", style={"display": "none"}, children=[
                html.Div(className="sira-historial-nav", children=[
                    html.A("← Volver al dashboard", href="/", className="sira-link-nav"),
                    html.A("Estado del sistema", href="/status", className="sira-link-nav"),
                ]),
                html.Div(className="sira-charts-row sira-charts-row--historial", children=[
                    bloque(
                        "historial", "Evolución 30 días — municipio seleccionado",
                        "Score sísmico máximo diario e índice de riesgo meteorológico.",
                        accent=C_CYAN,
                    ),
                ]),
            ]),
        ]),
    ]),
    html.Footer(className="sira-footer", children=[
        html.P("© 2026 SIRA — Sistema Ibérico de Riesgos y Alerta. Todos los derechos reservados."),
    ]),
])


def _load() -> dict:
    try:
        r = requests.get(f"{API_BASE_URL}/api/dashboard", timeout=30)
        if r.ok:
            return r.json()
    except requests.RequestException:
        pass
    return read_dashboard()


def _meteo_para_geo(municipio_id: str, localidad: str | None = None) -> dict:
    """GET /api/meteo/{municipio} al cambiar zona; fallback local si la API no responde."""
    mid = str(municipio_id or _DEFAULT_MUNI).zfill(5)
    params = {"localidad": localidad} if localidad else None
    try:
        r = requests.get(f"{API_BASE_URL}/api/meteo/{mid}", params=params, timeout=30)
        if r.ok:
            data = r.json()
            if isinstance(data, dict):
                return data
    except requests.RequestException:
        pass
    return meteo_localidad(mid, localidad)


def _es_sismo_hoy(ts) -> bool:
    try:
        return pd.to_datetime(ts, utc=True).date() == datetime.now(timezone.utc).date()
    except (ValueError, TypeError):
        return False


def _fmt_sismo_fecha(ts) -> str:
    try:
        return pd.to_datetime(ts, utc=True).strftime("%d/%m/%Y %H:%M UTC")
    except (ValueError, TypeError):
        return "—"


def _sismo_mag_max(sismos: list, mag_max: float) -> dict | None:
    if not sismos:
        return None
    candidatos = [s for s in sismos if s.get("magnitud") == mag_max]
    if not candidatos:
        candidatos = sismos
    return max(candidatos, key=lambda s: (s.get("score_local", s.get("score_total", 0)), s.get("magnitud", 0)))


def _detalle_sismo(sismo: dict | None) -> html.Div | str:
    if not sismo:
        return "Sin eventos en el periodo"
    return html.Div(className="sira-evento-info", children=[
        html.Div(_fmt_sismo_fecha(sismo.get("timestamp")), className="sira-evento-fecha"),
        html.Div(sismo.get("lugar") or "—", className="sira-evento-lugar"),
    ])


def _bloque_oce(oce: dict, clave: str) -> dict:
    bloque = oce.get(clave)
    if isinstance(bloque, dict) and bloque.get("serie_horaria") is not None:
        return bloque
    if clave == "MEDITERRÁNEO" and oce.get("serie_horaria") is not None:
        return oce
    return {"serie_horaria": [], "resumen": {}}


def _alertas_meteo_fuente(d: dict) -> list[dict]:
    """Avisos de prueba + live ya resueltos por read_dashboard/API (caché AEMET 90 s)."""
    local = list(d.get("meteo_alertas_test", [])) if isinstance(d.get("meteo_alertas_test"), list) else []
    live = list(d.get("meteo_alertas_live", [])) if isinstance(d.get("meteo_alertas_live"), list) else []
    return [*local, *live]


def _alertas_meteo_locales(geo: dict, alertas: list[dict]) -> list[dict]:
    geo = _geo_resuelto(geo)
    filtradas = [
        a for a in alertas
        if alerta_coincide_zona(
            a,
            provincia_id=geo.get("provincia_id"),
            municipio_id=geo.get("municipio_id"),
            provincia=geo.get("provincia"),
            municipio=geo.get("municipio"),
        )
    ]
    return deduplicar_alertas(filtradas)


def _data_refresh_token(d: dict, alertas: list[dict] | None = None) -> str:
    src = alertas if alertas is not None else _alertas_meteo_fuente(d)
    firmas = sorted(
        "|".join(alerta_firma(a))
        for a in src
        if isinstance(a, dict)
    )
    costa_sig = "|".join(
        f"{r['lat']:.2f},{r['lon']:.2f},{r['radio_tsunami_km']}"
        for r in alertas_a_capa_costera(src)
    )
    return (
        f"{d.get('generado_en', '—')}|{len(d.get('sismos', []))}|{len(d.get('incendios', []))}|{len(d.get('embalses', []))}|{len(d.get('aforos', []))}"
        f"|{'|'.join(firmas)}|{bool(d.get('sismo_prueba_activo'))}|prueba:{d.get('sismos_prueba_activos', 0)}|costa:{costa_sig}"
    )


def _riesgo_meteo_card(riesgo: dict) -> html.Div:
    elementos = riesgo.get("elementos") or []
    nivel_peligro = "amarillo"
    for e in elementos:
        n = str(e.get("nivel_peligro") or "").lower()
        if n == "rojo":
            nivel_peligro = "rojo"
            break
        if n == "naranja":
            nivel_peligro = "naranja"
    accent = {"rojo": "#ef4444", "naranja": C_ORANGE, "amarillo": "#eab308"}.get(
        nivel_peligro,
        COLORES.get(riesgo.get("nivel_global", riesgo.get("nivel", "MÍNIMO")), C_ORANGE),
    )
    h = riesgo.get("horas", RIESGO_METEO_HORAS)
    return card(
        "Riesgo meteorológico adverso",
        riesgo_meteo_panel(riesgo),
        riesgo.get("texto") or "",
        f"AEMET Meteoalerta + predicción horaria ({h} h).",
        accent=accent,
    )


def _add_circulos_perceptibles(
    fig: go.Figure,
    rows: pd.DataFrame,
    *,
    legend_name: str,
    legendgroup: str,
    period_ms: int,
    fill_rgb: str = "248, 113, 113",
    border_rgb: str = "220, 38, 38",
    radio_col: str = "radio_perceptible_km",
    hover_label: str = "Zona perceptible",
    show_legend: bool = True,
) -> None:
    """Disco + borde pulsante; animación vía pulse-map.js (meta.pulse=grow)."""
    if rows.empty:
        return
    radios = (
        rows[radio_col].tolist()
        if radio_col in rows.columns
        else [120.0] * len(rows)
    )
    for idx, row in enumerate(rows.itertuples(index=False)):
        r = float(radios[idx]) if idx < len(radios) else 120.0
        if r <= 0:
            continue
        lat0 = float(row.lat)
        lon0 = float(row.lon)
        mag = float(getattr(row, "magnitud", 0) or 0)
        row_hover = getattr(row, "hover_label", None) or hover_label
        area = getattr(row, "area_desc", "") or ""
        if mag > 0:
            hover_body = f"{row_hover} (hasta ~{r:.0f} km)<br>Mag {mag:.1f} · epicentro"
            if area:
                hover_body += f"<br>{area}"
        elif area:
            hover_body = f"{row_hover} (hasta ~{r:.0f} km)<br>{area}"
        else:
            hover_body = f"{row_hover} (hasta ~{r:.0f} km)"
        r0 = max(r * 0.06, 3.0)
        lat_fill, lon_fill = circle_disk_polygon(lat0, lon0, r0, MAP_CIRCLE_POINTS)
        lat_ring, lon_ring = circle_perimeter(lat0, lon0, r0, MAP_CIRCLE_POINTS)
        pulse_meta = {
            "center_lat": lat0,
            "center_lon": lon0,
            "radius_km": r,
            "period_ms": period_ms,
            "fill_rgb": fill_rgb,
            "border_rgb": border_rgb,
        }
        fig.add_trace(
            go.Scattergeo(
                lat=lat_fill,
                lon=lon_fill,
                mode="lines",
                name=legend_name,
                legendgroup=legendgroup,
                showlegend=show_legend and idx == 0,
                fill="toself",
                fillcolor=f"rgba({fill_rgb}, 0.08)",
                line=dict(width=0, color="rgba(0, 0, 0, 0)"),
                hovertemplate=hover_body + "<extra></extra>",
                meta={**pulse_meta, "pulse": "grow", "part": "fill"},
            )
        )
        fig.add_trace(
            go.Scattergeo(
                lat=lat_ring,
                lon=lon_ring,
                mode="lines",
                name=legend_name,
                legendgroup=legendgroup,
                showlegend=False,
                fill="none",
                line=dict(width=2, color=f"rgba({border_rgb}, 0.75)"),
                hoverinfo="skip",
                meta={**pulse_meta, "pulse": "grow", "part": "border", "radius_fraction": 1.0},
            )
        )


def _map_viewport(geo: dict | None) -> dict:
    zoom = (geo or {}).get("map_zoom")
    if zoom and zoom.get("lat_centro") is not None:
        return zoom
    muni_id = (geo or {}).get("municipio_id") or _DEFAULT_MUNI
    pid = str((geo or {}).get("provincia_id") or provincia_de_municipio(muni_id) or _DEFAULT_PROV).zfill(2)
    loc_id = (geo or {}).get("localidad_id")
    lat_obs, lon_obs, _ = coords_observacion(muni_id, loc_id)
    return viewport_ccaa_centro(pid, lat_obs, lon_obs, alejado=True)


def _geo_layout(fig: go.Figure, viewport: dict | None = None, *, uirevision: str = "sira-mapa") -> None:
    vp = viewport or {
        "lat_centro": MAPA["lat_centro"],
        "lon_centro": MAPA["lon_centro"],
        "lat_min": MAPA["lat_min"],
        "lat_max": MAPA["lat_max"],
        "lon_min": MAPA["lon_min"],
        "lon_max": MAPA["lon_max"],
    }
    if vp.get("centrar_obs"):
        vp = viewport_fit_observacion(vp, aspect=2.85)
    else:
        vp = viewport_fit_contenedor(vp, aspect=2.85)
    zoom_margin = 1.38 if vp.get("nivel") == "ccaa" else 1.0
    proj_scale = projection_scale_for_viewport(vp, margin=zoom_margin)
    fig.update_geos(
        scope="world",
        projection_type="mercator",
        center=dict(lat=vp["lat_centro"], lon=vp["lon_centro"]),
        projection_scale=proj_scale,
        lataxis_range=[vp["lat_min"], vp["lat_max"]],
        lonaxis_range=[vp["lon_min"], vp["lon_max"]],
        domain=dict(x=[0, 1], y=[0, 1]),
        showland=True, landcolor=C_NAVY,
        showocean=True, oceancolor="#1e4976",
        showcountries=False,
        showcoastlines=False,
        resolution=110,
    )
    fig.update_layout(
        margin=dict(t=10, b=0, l=0, r=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        autosize=True,
        uirevision=uirevision,
        **PLOTLY_BG,
    )


def _add_marcador_observacion(fig: go.Figure, lat_obs: float | None, lon_obs: float | None, obs_nombre: str) -> None:
    if lat_obs is not None and lon_obs is not None:
        fig.add_trace(go.Scattergeo(
            lat=[lat_obs], lon=[lon_obs], mode="markers+text",
            text=[obs_nombre or "Ubicación"], showlegend=False,
            marker=dict(size=11, color="#fbbf24", symbol="star", line=dict(width=1, color="white")),
            textposition="top center",
        ))


def _add_zona_incendio(fig: go.Figure, inc: dict, *, destacado: bool, legend_name: str | None = None) -> None:
    lat = float(inc["lat"])
    lon = float(inc["lon"])
    r = float(inc.get("radio_km") or 2)
    fill_rgb = "239, 68, 68" if destacado else "249, 115, 22"
    border_rgb = "220, 38, 38" if destacado else "234, 88, 12"
    if destacado:
        r_draw = max(r * 0.06, 1.5)
        fill_op = 0.12
        border_op = 0.75
        pulse_meta = {
            "center_lat": lat,
            "center_lon": lon,
            "radius_km": r,
            "period_ms": 2000,
            "fill_rgb": fill_rgb,
            "border_rgb": border_rgb,
        }
        fill_meta = {**pulse_meta, "pulse": "grow", "part": "fill"}
        border_meta = {**pulse_meta, "pulse": "grow", "part": "border", "radius_fraction": 1.0}
    else:
        r_draw = r
        fill_op = 0.16
        border_op = 1.0
        fill_meta = None
        border_meta = None
    lat_fill, lon_fill = circle_disk_polygon(lat, lon, r_draw, MAP_CIRCLE_POINTS)
    lat_ring, lon_ring = circle_perimeter(lat, lon, r_draw, MAP_CIRCLE_POINTS)
    fig.add_trace(go.Scattergeo(
        lat=lat_fill, lon=lon_fill, mode="lines", name=legend_name or "Foco",
        legendgroup="inc", showlegend=bool(legend_name),
        fill="toself", fillcolor=f"rgba({fill_rgb}, {fill_op})",
        line=dict(width=0, color="rgba(0, 0, 0, 0)"),
        hovertemplate=(
            f"Foco activo<br>"
            f"Radio ~{r:.1f} km · área ~{inc.get('area_km2', '—')} km²<br>"
            f"FRP {inc.get('frp_mw', '—')} MW · {inc.get('n_detecciones', 1)} detecciones"
            + (" · cerca de tu zona<extra></extra>" if destacado else "<extra></extra>")
        ),
        meta=fill_meta,
    ))
    fig.add_trace(go.Scattergeo(
        lat=lat_ring, lon=lon_ring, mode="lines", showlegend=False,
        fill="none",
        line=dict(width=2 if destacado else 1.6, color=f"rgba({border_rgb}, {border_op})"),
        hoverinfo="skip",
        meta=border_meta,
    ))


def _add_marcadores_embalses(fig: go.Figure, embalses: list[dict]) -> None:
    """Puntos azules para embalses en vigilancia (no círculos de radio)."""
    if not embalses:
        return
    colores = {
        "critico": "#1d4ed8",
        "alerta": "#2563eb",
        "vigilancia": "#38bdf8",
    }
    leyenda = False
    for emb in embalses:
        lat = float(emb.get("lat") or 0)
        lon = float(emb.get("lon") or 0)
        if not lat and not lon:
            continue
        nivel = str(emb.get("nivel_riesgo") or "vigilancia")
        color = colores.get(nivel, "#38bdf8")
        size = {"critico": 13, "alerta": 11, "vigilancia": 9}.get(nivel, 9)
        pct = emb.get("porcentaje", "—")
        vol = emb.get("volumen_hm3", "—")
        dist = emb.get("dist_local_km", "—")
        fig.add_trace(go.Scattergeo(
            lat=[lat],
            lon=[lon],
            mode="markers",
            name="Embalse en vigilancia" if not leyenda else None,
            legendgroup="embalses",
            showlegend=not leyenda,
            marker=dict(size=size, color=color, symbol="circle", line=dict(width=1.2, color="white")),
            text=[emb.get("nombre", "Embalse")],
            hovertemplate=(
                "%{text}<br>"
                f"Nivel: {pct}% · {vol} hm³<br>"
                f"Riesgo: {nivel.title()}<br>"
                f"Distancia: {dist} km"
                "<extra></extra>"
            ),
        ))
        leyenda = True


def _add_marcadores_aforos(fig: go.Figure, aforos: list[dict]) -> None:
    """Puntos verdes/teal para aforos CHJ con caudal en alerta."""
    if not aforos:
        return
    colores = {
        "critico": "#dc2626",
        "alerta": "#f97316",
        "vigilancia": "#14b8a6",
    }
    leyenda = False
    for af in aforos:
        lat = float(af.get("lat") or 0)
        lon = float(af.get("lon") or 0)
        if not lat and not lon:
            continue
        nivel = str(af.get("nivel_riesgo") or "vigilancia")
        sin_datos = bool(af.get("sin_datos_recientes"))
        if sin_datos:
            color = "#f59e0b"
            symbol = "x"
            size = 10
            tipo_txt = "Aforo — sensor sin datos"
        else:
            color = colores.get(nivel, "#14b8a6")
            symbol = "diamond"
            size = {"critico": 12, "alerta": 10, "vigilancia": 8}.get(nivel, 8)
            tipo_txt = "Aforo CHJ"
        q = af.get("caudal_m3s")
        h = af.get("nivel_m")
        dist = af.get("dist_local_km", "—")
        q_txt = f"{q} m³/s" if q is not None else "—"
        h_txt = f"{h} m" if h is not None else "—"
        fig.add_trace(go.Scattergeo(
            lat=[lat],
            lon=[lon],
            mode="markers",
            name="Aforo CHJ en alerta" if not leyenda else None,
            legendgroup="aforos",
            showlegend=not leyenda,
            marker=dict(size=size, color=color, symbol=symbol, line=dict(width=1.2, color="white")),
            text=[af.get("nombre", "Aforo")],
            hovertemplate=(
                f"{tipo_txt}<br>"
                "%{text}<br>"
                f"Nivel: {h_txt} · Caudal: {q_txt}<br>"
                f"Riesgo: {nivel.title()}{' · sin lectura reciente' if sin_datos else ''}<br>"
                f"Distancia: {dist} km"
                "<extra></extra>"
            ),
        ))
        leyenda = True


def _fig_mapa(
    sismos: list,
    incendios: list | None = None,
    lat_obs: float | None = None,
    lon_obs: float | None = None,
    obs_nombre: str = "",
    zonas_costeras: list | None = None,
    embalses_mapa: list | None = None,
    aforos_mapa: list | None = None,
    viewport: dict | None = None,
    map_uirevision: str = "sira-mapa",
    provincia_id: str | None = None,
) -> go.Figure:
    fig = go.Figure()
    anadir_costa_ign(fig, viewport)
    anadir_bordes_ccaa(fig, provincia_id)
    anadir_bordes_provincias(fig, provincia_id)
    df = pd.DataFrame(sismos) if sismos else pd.DataFrame()
    hoy_df = pd.DataFrame()

    if not df.empty and "nivel_local" not in df.columns:
        df = df.copy()
        if "nivel_alerta" in df.columns:
            df["nivel_local"] = df["nivel_alerta"]
        if "score_total" in df.columns:
            df["score_local"] = df["score_total"]

    if not df.empty and "es_prueba" in df.columns:
        mask_prueba = df["es_prueba"].fillna(False)
        df_prueba = df[mask_prueba]
        df = df[~mask_prueba]
    else:
        df_prueba = pd.DataFrame()

    if not df.empty and "perceptible_local" in df.columns:
        en_mar_col = df["en_mar"].fillna(False) if "en_mar" in df.columns else False
        perceptible_tierra = df["perceptible_local"].fillna(False)
        tsunami_mar = (
            df["alerta_tsunami"].fillna(False) & en_mar_col
            if "alerta_tsunami" in df.columns
            else False
        )
        hoy_col = (
            df["timestamp"].map(_es_sismo_hoy)
            if "timestamp" in df.columns
            else pd.Series([False] * len(df), index=df.index)
        )
        radio_col = (
            df["radio_perceptible_km"].fillna(0)
            if "radio_perceptible_km" in df.columns
            else pd.Series([0.0] * len(df), index=df.index)
        )
        hoy_tierra_zona = hoy_col & ~en_mar_col & (radio_col > 0)
        mask_mapa = perceptible_tierra | tsunami_mar | hoy_tierra_zona
        df_per = df[mask_mapa]
    else:
        df_per = df

    inc_list = incendios or []
    if inc_list:
        leyenda_inc = False
        for inc in sorted(inc_list, key=lambda x: (-float(x.get("frp_mw") or 0),))[:INCENDIO_MAP_MAX]:
            _add_zona_incendio(
                fig, inc, destacado=bool(inc.get("afecta_local")),
                legend_name="Incendio activo" if not leyenda_inc else None,
            )
            leyenda_inc = True

    for nivel, color in COLORES.items():
        sub = df_per[df_per["nivel_local"] == nivel] if not df_per.empty else pd.DataFrame()
        if sub.empty:
            continue
        reg_col = sub["region"] if "region" in sub.columns else [""] * len(sub)
        fechas = [_fmt_sismo_fecha(ts) for ts in sub["timestamp"]] if "timestamp" in sub.columns else ["—"] * len(sub)
        dist_loc = sub["dist_local_km"] if "dist_local_km" in sub.columns else [""] * len(sub)
        hoy_mask = [_es_sismo_hoy(ts) for ts in sub["timestamp"]] if "timestamp" in sub.columns else [False] * len(sub)
        base = sub["magnitud"] * 2 + 5
        sizes = [9 if h else b for b, h in zip(base, hoy_mask)]
        borders = [("white", 1) if h else ("white", 0.5) for h in hoy_mask]
        fig.add_trace(go.Scattergeo(
            lat=sub["lat"], lon=sub["lon"], mode="markers", name=nivel,
            marker=dict(
                size=sizes, color=color,
                line=dict(width=[b[1] for b in borders], color=[b[0] for b in borders]),
            ),
            text=sub["lugar"],
            customdata=list(zip(sub["magnitud"], sub["score_local"], reg_col, fechas, dist_loc)),
            hovertemplate=(
                "Sismo — %{text}<br>"
                "Fecha: %{customdata[3]}<br>"
                "Mag %{customdata[0]} · Score local %{customdata[1]} · %{customdata[2]}<br>"
                "Distancia: %{customdata[4]} km"
                "<extra></extra>"
            ),
        ))

    if not df_per.empty and "timestamp" in df_per.columns:
        hoy_df = df_per[df_per["timestamp"].map(_es_sismo_hoy)]
    else:
        hoy_df = pd.DataFrame()

    if not hoy_df.empty:
        if "en_mar" in hoy_df.columns:
            hoy_perceptible = hoy_df[~hoy_df["en_mar"].fillna(False)]
        else:
            hoy_perceptible = hoy_df
        if not hoy_perceptible.empty:
            _add_circulos_perceptibles(
                fig,
                hoy_perceptible,
                legend_name="Zona perceptible (hoy)",
                legendgroup="hoy",
                period_ms=1600,
            )

        if "alerta_tsunami" in hoy_df.columns:
            mask_tsunami = hoy_df["alerta_tsunami"].fillna(False)
            if "en_mar" in hoy_df.columns:
                mask_tsunami = mask_tsunami & hoy_df["en_mar"].fillna(False)
            df_tsunami = hoy_df[mask_tsunami]
            if not df_tsunami.empty:
                _add_circulos_perceptibles(
                    fig,
                    df_tsunami,
                    legend_name="Alerta tsunami (hoy)",
                    legendgroup="tsunami",
                    period_ms=1800,
                    fill_rgb="96, 165, 250",
                    border_rgb="37, 99, 235",
                    radio_col="radio_tsunami_km",
                    hover_label="Alerta tsunami",
                )

    if zonas_costeras:
        df_costa = pd.DataFrame(zonas_costeras)
        if not df_costa.empty:
            _add_circulos_perceptibles(
                fig,
                df_costa,
                legend_name="Aviso mar AEMET",
                legendgroup="costa_aemet",
                period_ms=2000,
                fill_rgb="96, 165, 250",
                border_rgb="37, 99, 235",
                radio_col="radio_tsunami_km",
                hover_label="Aviso mar",
            )

    if embalses_mapa:
        _add_marcadores_embalses(fig, embalses_mapa)

    if aforos_mapa:
        _add_marcadores_aforos(fig, aforos_mapa)

    if not df_prueba.empty:
        reg_col = df_prueba["region"] if "region" in df_prueba.columns else [""] * len(df_prueba)
        fechas = [_fmt_sismo_fecha(ts) for ts in df_prueba["timestamp"]] if "timestamp" in df_prueba.columns else ["—"] * len(df_prueba)
        dist_loc = df_prueba["dist_local_km"] if "dist_local_km" in df_prueba.columns else [""] * len(df_prueba)
        hoy_mask_prueba = (
            [_es_sismo_hoy(ts) for ts in df_prueba["timestamp"]]
            if "timestamp" in df_prueba.columns
            else [False] * len(df_prueba)
        )
        df_prueba_hoy = df_prueba[hoy_mask_prueba] if len(hoy_mask_prueba) else pd.DataFrame()
        if not df_prueba_hoy.empty:
            _add_circulos_perceptibles(
                fig,
                df_prueba_hoy,
                legend_name="Zona perceptible (prueba)",
                legendgroup="prueba",
                period_ms=1400,
                show_legend=False,
            )
        prueba_sizes = [9 if h else (m * 2 + 8) for m, h in zip(df_prueba["magnitud"], hoy_mask_prueba)]
        prueba_borders = [("white", 1) if h else ("#f87171", 2) for h in hoy_mask_prueba]
        fig.add_trace(go.Scattergeo(
            lat=df_prueba["lat"], lon=df_prueba["lon"], mode="markers", name="Prueba",
            marker=dict(
                size=prueba_sizes,
                color="rgba(239, 68, 68, 0.9)",
                symbol="circle",
                line=dict(width=[b[1] for b in prueba_borders], color=[b[0] for b in prueba_borders]),
            ),
            text=df_prueba["lugar"],
            customdata=list(zip(df_prueba["magnitud"], df_prueba["score_local"], reg_col, fechas, dist_loc)),
            hovertemplate=(
                "🧪 %{text}<br>"
                "Fecha: %{customdata[3]}<br>"
                "Mag %{customdata[0]} · Score local %{customdata[1]} · %{customdata[2]}<br>"
                "Distancia: %{customdata[4]} km"
                "<extra></extra>"
            ),
        ))

    _add_marcador_observacion(fig, lat_obs, lon_obs, obs_nombre)
    from sismos import distancia_km

    refs: list[tuple[float, float, str, str]] = []
    if lat_obs is not None and lon_obs is not None:
        if distancia_km(lat_obs, lon_obs, ZONA["lat_ref"], ZONA["lon_ref"]) < 8:
            refs.append((ZONA["lat_ref"], ZONA["lon_ref"], ZONA["ciudad_ref"], C_CYAN))
    for lat, lon, name, color in refs:
        fig.add_trace(go.Scattergeo(
            lat=[lat], lon=[lon], mode="markers+text", text=[name], showlegend=False,
            marker=dict(size=10, color=color, symbol="star"),
        ))
    _geo_layout(fig, viewport, uirevision=map_uirevision)
    fig.update_layout(legend=dict(title="Alerta", orientation="h", yanchor="bottom", y=1.02, x=0))
    return fig


def _color_sst(temp_c: float | None) -> str:
    if temp_c is None:
        return C_MUTED
    if temp_c >= 26:
        return SEMAFORO_COLORES["ROJO"]
    if temp_c >= 23:
        return SEMAFORO_COLORES["NARANJA"]
    if temp_c >= 20:
        return SEMAFORO_COLORES["AMARILLO"]
    return SEMAFORO_COLORES["VERDE"]


def _color_corriente(vel_ms: float | None) -> str:
    if vel_ms is None:
        return C_MUTED
    if vel_ms >= 1.0:
        return SEMAFORO_COLORES["ROJO"]
    if vel_ms >= 0.6:
        return SEMAFORO_COLORES["NARANJA"]
    if vel_ms >= 0.3:
        return SEMAFORO_COLORES["AMARILLO"]
    return SEMAFORO_COLORES["VERDE"]


def _annots_ultima_con_semaforo(texto: str, color_dot: str) -> list[dict]:
    """Círculo de color + lectura neutra, alineados a la derecha del gráfico."""
    pad = max(72, int(len(texto) * 6.2))
    return [
        dict(
            text=texto,
            xref="paper", yref="paper", x=1, y=1.12,
            xanchor="right", showarrow=False,
            font=dict(color=C_TEXT, size=11),
        ),
        dict(
            text="●",
            xref="paper", yref="paper", x=1, y=1.12,
            xanchor="right", xshift=-pad, showarrow=False,
            font=dict(color=color_dot, size=13),
        ),
    ]


def _fig_corrientes(serie: list, uirev: str) -> go.Figure:
    fig = go.Figure()
    dir_txt = "—"
    ult_txt = "Última: — m/s"
    dot_color = C_MUTED
    if serie:
        s = pd.DataFrame(serie)
        s["timestamp"] = pd.to_datetime(s["timestamp"], errors="coerce")
        fig.add_trace(go.Scatter(
            x=s["timestamp"], y=s["corriente_vel_ms"],
            mode="lines", name="m/s", line=dict(color=C_GREEN),
        ))
        vel = s["corriente_vel_ms"].dropna()
        if not vel.empty:
            ult_val = float(vel.iloc[-1])
            dot_color = _color_corriente(ult_val)
            ult_txt = f"Última: {ult_val:.2f} m/s"
        if s["corriente_dir_grados"].notna().any():
            dir_txt = dir_compass(s["corriente_dir_grados"].dropna().iloc[-1])
    annotations = [
        dict(
            text=f"Dirección: {dir_txt}",
            xref="paper", yref="paper", x=0, y=1.12,
            showarrow=False, font=dict(color=C_GREEN, size=11),
        ),
        *_annots_ultima_con_semaforo(ult_txt, dot_color),
    ]
    fig.update_layout(
        margin=dict(t=28, b=0, l=0, r=0),
        autosize=True,
        yaxis_title="m/s",
        uirevision=uirev,
        annotations=annotations,
        **PLOTLY_BG,
    )
    return fig


def _stats_region(sismos: list) -> dict[str, int]:
    reg: dict[str, int] = {}
    for s in sismos:
        r = s.get("region", "")
        reg[r] = reg.get(r, 0) + 1
    return reg


def _fig_linea(serie: list, campo: str, color: str, unidad: str, uirev: str, *, con_semaforo_sst: bool = False) -> go.Figure:
    fig = go.Figure()
    ult_txt = f"Última: — {unidad}"
    dot_color = C_MUTED
    if serie:
        s = pd.DataFrame(serie)
        s["timestamp"] = pd.to_datetime(s["timestamp"], errors="coerce")
        fig.add_trace(go.Scatter(x=s["timestamp"], y=s[campo], mode="lines", line=dict(color=color)))
        vals = s[campo].dropna()
        if not vals.empty:
            ult_val = float(vals.iloc[-1])
            ult_txt = f"Última: {ult_val:.2f} {unidad}"
            if con_semaforo_sst:
                dot_color = _color_sst(ult_val)
    if con_semaforo_sst:
        annotations = _annots_ultima_con_semaforo(ult_txt, dot_color)
    else:
        annotations = [dict(
            text=ult_txt,
            xref="paper", yref="paper",
            x=1, y=1.12,
            xanchor="right",
            showarrow=False,
            font=dict(color=C_TEXT, size=11),
        )]
    fig.update_layout(
        margin=dict(t=28, b=0, l=0, r=0),
        autosize=True,
        yaxis_title=unidad,
        uirevision=uirev,
        annotations=annotations,
        **PLOTLY_BG,
    )
    return fig


def _fig_historial(municipio_id: str | None, uirev: str) -> go.Figure:
    fig = go.Figure()
    mid = str(municipio_id or _DEFAULT_MUNI).zfill(5)
    serie = get_historial_municipio(mid, 30)
    if serie:
        fechas = [r["fecha"] for r in serie]
        fig.add_trace(go.Scatter(
            x=fechas, y=[r["score_sismo_max"] for r in serie],
            mode="lines+markers", name="Score sísmico máx.",
            line=dict(color=C_ORANGE),
        ))
        fig.add_trace(go.Scatter(
            x=fechas, y=[r["indice_riesgo_meteo"] for r in serie],
            mode="lines+markers", name="Índice riesgo meteo",
            line=dict(color=C_TEAL), yaxis="y2",
        ))
    fig.update_layout(
        margin=dict(t=10, b=0, l=0, r=0),
        autosize=True,
        uirevision=uirev,
        yaxis=dict(title="Score", rangemode="tozero"),
        yaxis2=dict(title="Índice", overlaying="y", side="right", range=[0, 100]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        **PLOTLY_BG,
    )
    return fig


_MESES_EJE_LLUVIA = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def _xaxis_lluvia(timestamps: pd.Series) -> dict:
    ts = timestamps.dropna().sort_values().reset_index(drop=True)
    if ts.empty:
        return {"type": "date"}

    pick_idx = [0]
    for i in range(1, len(ts)):
        dt = pd.Timestamp(ts.iloc[i])
        if dt.minute != 0 or dt.hour % 6 != 0:
            continue
        last = pd.Timestamp(ts.iloc[pick_idx[-1]])
        if (dt - last).total_seconds() >= 5 * 3600:
            pick_idx.append(i)

    tickvals = ts.iloc[pick_idx]
    ticktext: list[str] = []
    prev_date = None
    for i, tv in enumerate(tickvals):
        dt = pd.Timestamp(tv)
        d = dt.date()
        if i == 0 or prev_date is None or d != prev_date:
            mes = _MESES_EJE_LLUVIA[dt.month - 1]
            ticktext.append(f"{dt.day:02d}-{mes} {dt.strftime('%H:%M')}")
        else:
            ticktext.append(dt.strftime("%H:%M"))
        prev_date = d

    return {
        "type": "date",
        "tickmode": "array",
        "tickvals": tickvals.tolist(),
        "ticktext": ticktext,
        "tickangle": -90,
        "tickfont": dict(size=9, color=C_MUTED),
    }


def _fig_lluvia(serie: list) -> go.Figure:
    fig = go.Figure()
    yaxis = dict(title="mm", rangemode="tozero")
    if serie:
        s = pd.DataFrame(serie)
        s["timestamp"] = pd.to_datetime(s["timestamp"], errors="coerce")
        precip = s["precip_mm"].fillna(0)
        fig.add_trace(go.Bar(x=s["timestamp"], y=precip, name="mm", marker_color=C_TEAL))
        if s["prob_precip_pct"].notna().any():
            fig.add_trace(go.Scatter(x=s["timestamp"], y=s["prob_precip_pct"], name="%", yaxis="y2", line=dict(color="#a78bfa")))
        max_precip = float(precip.max())
        yaxis["range"] = [0, max(1.0, max_precip * 1.15)]
        xaxis = _xaxis_lluvia(s["timestamp"])
    else:
        xaxis = {"type": "date"}
    fig.update_layout(
        margin=dict(t=10, b=58, l=0, r=0),
        autosize=True,
        xaxis=xaxis,
        yaxis=yaxis,
        yaxis2=dict(overlaying="y", side="right", range=[0, 100], title="%"),
        uirevision="sira-lluvia",
        **PLOTLY_BG,
    )
    return fig


@callback(
    Output("geo-municipio", "options"),
    Output("geo-municipio", "value"),
    Input("geo-provincia", "value"),
    State("geo-municipio", "value"),
)
def on_provincia(provincia_id, current_muni):
    if not provincia_id:
        return opciones([], "Municipio"), None
    munis = municipios(provincia_id)
    opts = opciones(munis, "Municipio")
    if not munis:
        return opts, None
    ids = {str(m["id"]) for m in munis}
    cur = str(current_muni) if current_muni else None
    if cur in ids:
        return opts, cur
    return opts, str(munis[0]["id"])


@callback(
    Output("geo-localidad", "options"),
    Output("geo-localidad", "value"),
    Input("geo-municipio", "value"),
    State("geo-localidad", "value"),
)
def on_municipio(municipio_id, current_loc):
    if not municipio_id:
        return opciones([], "Localidad"), None
    locs = localidades(municipio_id)
    opts = opciones(locs, "Localidad")
    if not locs:
        return opts, None
    ids = {str(l["id"]) for l in locs}
    cur = str(current_loc) if current_loc else None
    if cur in ids:
        return opts, cur
    return opts, str(locs[0]["id"])


@callback(
    Output("geo-store", "data"),
    Input("geo-provincia", "value"),
    Input("geo-municipio", "value"),
    Input("geo-localidad", "value"),
)
def on_geo_change(provincia_id, municipio_id, localidad_id):
    prov = next((p for p in provincias() if p["id"] == str(provincia_id or "").zfill(2)), None)
    muni = municipio_por_id(municipio_id)
    locs = localidades(municipio_id)
    loc = next((l for l in locs if l["id"] == localidad_id), locs[0] if locs else None)
    lat_obs, lon_obs, _ = coords_observacion(municipio_id, localidad_id)
    trigger = ctx.triggered_id
    if trigger in ("geo-provincia", "geo-municipio", "geo-localidad"):
        map_zoom = viewport_ccaa_centro(provincia_id, lat_obs, lon_obs, alejado=True)
    else:
        map_zoom = viewport_ccaa_centro(
            provincia_id or _DEFAULT_PROV, lat_obs, lon_obs, alejado=True,
        )
    return {
        "provincia_id": provincia_id,
        "provincia": prov["nombre"] if prov else None,
        "municipio_id": municipio_id,
        "municipio": muni["nombre"] if muni else None,
        "localidad_id": localidad_id,
        "localidad": loc["nombre"] if loc else None,
        "map_zoom": map_zoom,
    }


@callback(
    Output("page-home", "style"),
    Output("page-historial", "style"),
    Output("tick", "disabled"),
    Output("geo-locate-poll", "disabled"),
    Input("url", "pathname"),
)
def route_pages(pathname):
    on_historial = pathname == "/historial"
    if on_historial:
        return {"display": "none"}, {"display": "block"}, True, True
    return {"display": "block"}, {"display": "none"}, False, True


@callback(
    Output("geo-locate-poll", "disabled", allow_duplicate=True),
    Input("geo-locate-btn", "n_clicks"),
    prevent_initial_call=True,
)
def _activar_poll_geo(_n):
    return False


@callback(
    Output("historial", "figure"),
    Input("url", "pathname"),
    Input("geo-municipio", "value"),
)
def refresh_historial(pathname, municipio_id):
    if pathname != "/historial":
        raise PreventUpdate
    return _fig_historial(municipio_id or _DEFAULT_MUNI, "sira-historial")


def _build_panel_geo(geo: dict, d: dict) -> tuple[list, go.Figure, go.Figure]:
    """Tarjetas, mapa y lluvia según la zona seleccionada."""
    geo = _geo_resuelto(geo)
    muni_id = geo.get("municipio_id") or _DEFAULT_MUNI
    localidad = geo.get("localidad") or ZONA["ciudad_ref"]
    lat_obs, lon_obs, _ = coords_observacion(muni_id, geo.get("localidad_id"))

    sismos_all = d.get("sismos", [])
    sismos_mapa = [enriquecer_local(s, lat_obs, lon_obs) for s in sismos_all]
    sismos_mapa = [
        anexar_boletin_tsunami(s, lat_obs, lon_obs, muni_id)
        if s.get("alerta_tsunami")
        else s
        for s in sismos_mapa
    ]
    for s in sismos_mapa:
        if s.get("alerta_tsunami") and s.get("tsunami_texto_ola"):
            s["area_desc"] = str(s["tsunami_texto_ola"])
    sismos = [s for s in sismos_mapa if s.get("perceptible_local")]
    incendios_all = d.get("incendios", [])
    incendios_mapa = [enriquecer_incendio_local(i, lat_obs, lon_obs) for i in incendios_all]
    incendios_local = [i for i in incendios_mapa if i.get("cerca_local")]
    embalses_all = d.get("embalses", [])
    aforos_all = d.get("aforos", [])
    met = _meteo_para_geo(muni_id, localidad)
    res_met = met.get("resumen", {})
    lluvia_24 = float(res_met.get("precip_prox_24h_mm") or 0)
    res_emb = resumen_embalses(embalses_all, lat_obs, lon_obs, lluvia_24h_mm=lluvia_24)
    res_afor = resumen_aforos(aforos_all, lat_obs, lon_obs)
    embalses_mapa = embalses_para_mapa(embalses_all, lat_obs, lon_obs, lluvia_24h_mm=lluvia_24)
    aforos_mapa = aforos_para_mapa(aforos_all, lat_obs, lon_obs)
    alertas_fuente = _alertas_meteo_fuente(d)
    alertas_meteo = _alertas_meteo_locales(geo, alertas_fuente)
    zonas_costeras = alertas_a_capa_costera(alertas_fuente)

    mag_max = max((s["magnitud"] for s in sismos), default=0)
    sismo_max = _sismo_mag_max(sismos, mag_max)
    nivel_max = sismo_max.get("nivel_local", sismo_max.get("nivel_alerta")) if sismo_max else None
    loc_label = f"{localidad}, {geo.get('municipio') or ''}".strip(", ")

    cards = [
        card_sismos_combinada(
            len(sismos_all),
            len(sismos),
            localidad,
            float(mag_max),
            nivel_max,
            _detalle_sismo(sismo_max),
            "",
            accent=C_ORANGE,
        ),
        card_doble(
            "Incendios activos",
            len(incendios_all),
            "España",
            len(incendios_local),
            f"cerca · {localidad}",
            f"NASA FIRMS · radio del foco ∝ área afectada · zona local ≤ {INCENDIO_RADIO_LOCAL_KM:.0f} km.",
            accent="#ea580c",
        ),
        card(
            "Lluvia 24h",
            lluvia_embalses_valor(res_met.get("precip_prox_24h_mm", "—"), res_emb, res_afor),
            f"Prob. máx. {res_met.get('prob_max_pct', '—')}% · {met.get('fuente', '—')}",
            f"{loc_label} · SAIH CHJ · embalses {EMBALSE_RADIO_LOCAL_KM:.0f} km · aforos {AFORO_RADIO_LOCAL_KM:.0f} km",
            accent=C_TEAL,
        ),
        card(
            "Tiempo ahora",
            meteo_ahora(res_met),
            f"Según {met.get('fuente', '—')} · {loc_label}",
            "Estado del cielo, temperatura, sensación térmica, humedad y viento en la localidad seleccionada.",
            accent=C_CYAN,
        ),
    ]
    riesgo_meteo = calcular_riesgo_meteo(alertas_meteo, met, horas=RIESGO_METEO_HORAS)
    cards.append(_riesgo_meteo_card(riesgo_meteo))

    viewport = _map_viewport(geo)
    map_rev = f"sira-mapa-{muni_id}-{viewport.get('nivel', 'municipio')}"
    mapa = _fig_mapa(
        sismos_mapa, incendios_mapa, lat_obs, lon_obs, localidad, zonas_costeras,
        embalses_mapa, aforos_mapa, viewport=viewport, map_uirevision=map_rev,
        provincia_id=geo.get("provincia_id"),
    )
    lluvia = _fig_lluvia(met.get("serie_horaria", []))
    return cards, mapa, lluvia


@callback(
    Output("cards", "children", allow_duplicate=True),
    Output("mapa", "figure", allow_duplicate=True),
    Output("lluvia", "figure", allow_duplicate=True),
    Input("geo-store", "data"),
    State("url", "pathname"),
    prevent_initial_call=True,
)
def refresh_geo(geo, pathname):
    if pathname == "/historial":
        raise PreventUpdate
    d = _load()
    return _build_panel_geo(geo, d)


@callback(
    Output("cards", "children"), Output("ts", "children"), Output("data-ts-store", "data"),
    Output("mapa", "figure"), Output("lluvia", "figure"),
    Output("sst_med", "figure"), Output("sst_cant", "figure"), Output("sst_atl", "figure"),
    Output("cor_med", "figure"), Output("cor_cant", "figure"), Output("cor_atl", "figure"),
    Input("tick", "n_intervals"), Input("btn", "n_clicks"),
    State("geo-store", "data"),
    State("data-ts-store", "data"),
    State("url", "pathname"),
)
def refresh(n_intervals, clicks, geo, last_ts, pathname):
    if pathname == "/historial":
        raise PreventUpdate
    if ALLOW_DATA_REFRESH and ctx.triggered_id == "btn" and clicks:
        try:
            requests.post(
                f"{API_BASE_URL}/api/actualizar",
                headers={"X-API-Key": API_KEY},
                timeout=120,
            )
        except requests.RequestException:
            pass

    d = _load()
    alertas_fuente = _alertas_meteo_fuente(d)
    refresh_token = _data_refresh_token(d, alertas_fuente)
    if ctx.triggered_id == "tick" and n_intervals and last_ts == refresh_token:
        raise PreventUpdate

    geo = _geo_resuelto(geo)
    cards, mapa, lluvia = _build_panel_geo(geo, d)
    oce = d.get("oceanografia", {})
    ts = fmt_ingesta_local(d.get("generado_en"))
    if d.get("sismo_prueba_activo"):
        ts = f"{ts} · Sismo de prueba en mapa"

    oce_med = _bloque_oce(oce, "MEDITERRÁNEO")
    oce_cant = _bloque_oce(oce, "CANTÁBRICO")
    oce_atl = _bloque_oce(oce, "ATLÁNTICO")

    return (
        cards, ts, refresh_token,
        mapa,
        lluvia,
        _fig_linea(oce_med.get("serie_horaria", []), "sst_c", C_ORANGE, "°C", "sira-sst-med", con_semaforo_sst=True),
        _fig_linea(oce_cant.get("serie_horaria", []), "sst_c", C_GREEN, "°C", "sira-sst-cant", con_semaforo_sst=True),
        _fig_linea(oce_atl.get("serie_horaria", []), "sst_c", C_CYAN, "°C", "sira-sst-atl", con_semaforo_sst=True),
        _fig_corrientes(oce_med.get("serie_horaria", []), "sira-cor-med"),
        _fig_corrientes(oce_cant.get("serie_horaria", []), "sira-cor-cant"),
        _fig_corrientes(oce_atl.get("serie_horaria", []), "sira-cor-atl"),
    )


if __name__ == "__main__":
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, debug=False)


# WSGI (gunicorn en Render)
server = app.server


@server.route("/sw.js")
def _service_worker():
    resp = send_from_directory(str(_ASSETS), "sw.js")
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


# Huella SHA-256 del keystore debug (añade la de release al publicar en Play Store).
_ANDROID_SHA256_DEBUG = (
    "30:20:B7:AC:BD:FB:CF:A4:90:77:A2:20:6F:F0:73:10:"
    "B3:A0:A7:87:78:8E:E0:48:3F:B1:50:B8:D9:0E:F8:D4"
)


@server.route("/.well-known/assetlinks.json")
def _assetlinks():
    return jsonify(
        [
            {
                "relation": ["delegate_permission/common.handle_all_urls"],
                "target": {
                    "namespace": "android_app",
                    "package_name": "es.sira.alertas",
                    "sha256_cert_fingerprints": [_ANDROID_SHA256_DEBUG],
                },
            }
        ]
    )


_FUENTE_ETIQUETAS = {
    "usgs": "USGS (sismos)",
    "aemet_meteo": "AEMET meteo",
    "aemet_cap": "AEMET CAP",
    "open_meteo_marine": "Open-Meteo marine",
    "open_meteo_weather": "Open-Meteo weather",
    "firms": "NASA FIRMS",
    "embals_es": "embals.es",
    "saih_chj": "SAIH CHJ",
}

_FUENTE_DESCRIPCIONES = {
    "usgs": "Sismos recientes en España y entorno (magnitud, epicentro, profundidad, alerta tsunami USGS).",
    "aemet_meteo": "Predicción horaria municipal AEMET (lluvia, probabilidad de precipitación, tiempo actual).",
    "aemet_cap": "Avisos Meteoalerta CAP por zona (temperatura, viento, lluvia, costa, tormentas, etc.).",
    "open_meteo_marine": "Temperatura superficial del mar y corrientes (Mediterráneo, Cantábrico, Atlántico).",
    "open_meteo_weather": "Previsión horaria de precipitación (respaldo cuando AEMET no está disponible).",
    "firms": "Puntos de calor e incendios activos detectados por satélite en territorio español.",
    "embals_es": "Niveles, capacidad y riesgo hidrológico de embalses (cuencas Júcar, Segura y Ebro).",
    "saih_chj": "Caudales y estaciones de aforo en tiempo casi real (SAIH, Confederación Hidrográfica del Júcar).",
}


def _status_snapshot() -> dict:
    """Lee estado desde API; fallback local si no responde."""
    try:
        r = requests.get(f"{API_BASE_URL}/api/status", timeout=15)
        if r.ok:
            payload = r.json()
            if isinstance(payload, dict):
                return payload
    except requests.RequestException:
        pass
    data = read_dashboard()
    return {
        "generado_en": data.get("generado_en", "—"),
        "fuentes_estado": data.get("fuentes_estado") if isinstance(data.get("fuentes_estado"), dict) else {},
        "suscripciones_push": count_subscriptions(),
        "ok": bool(data.get("generado_en")),
    }


def _fmt_status_dt(value: str | None) -> str:
    return fmt_ingesta_local(value)


@server.route("/status")
def _status_page():
    data = _status_snapshot()
    fuentes = data.get("fuentes_estado") if isinstance(data.get("fuentes_estado"), dict) else {}
    generado = _fmt_status_dt(data.get("generado_en"))
    n_push = data.get("suscripciones_push", 0)
    filas = []
    for clave, etiqueta in _FUENTE_ETIQUETAS.items():
        info = fuentes.get(clave, {})
        desc = _FUENTE_DESCRIPCIONES.get(clave, "—")
        ok = info.get("ok")
        if info.get("omitido"):
            estado = '<span class="sira-status-warn">omitido</span>'
        elif ok:
            n = info.get("registros", "—")
            estado = f'<span class="sira-status-ok">OK</span> <span class="sira-status-meta">({n} registros)</span>'
        else:
            err = info.get("error") or "error"
            estado = f'<span class="sira-status-fail">ERROR</span> <span class="sira-status-meta">{err}</span>'
        filas.append(
            f'<tr><td>{etiqueta}</td><td class="sira-status-desc">{desc}</td><td>{estado}</td></tr>'
        )
    tabla = "\n".join(filas)
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SIRA — Estado del sistema</title>
  <link rel="stylesheet" href="/assets/sira.css?v=32">
</head>
<body class="sira-page sira-status-page">
  <main class="sira-main">
    <div class="sira-container">
      <h1 class="sira-title">Estado del sistema</h1>
      <p class="sira-status-ts">Última ingesta: <strong>{generado}</strong> <span class="sira-ts-badge">Hora local</span></p>
      <p class="sira-status-ts">Suscripciones push activas: <strong>{n_push}</strong></p>
      <table class="sira-status-table">
        <thead><tr><th>Fuente</th><th>Descripción</th><th>Estado</th></tr></thead>
        <tbody>{tabla}</tbody>
      </table>
      <p class="sira-status-back"><a href="/">← Volver al dashboard</a></p>
    </div>
  </main>
</body>
</html>"""
    from flask import Response
    return Response(html, mimetype="text/html")


@server.route("/manifest.webmanifest")
def _manifest():
    return jsonify(
        {
            "name": "SIRA — Sistema Ibérico de Riesgos y Alerta",
            "short_name": "SIRA",
            "start_url": "/",
            "scope": "/",
            "display": "standalone",
            "background_color": "#0a1628",
            "theme_color": "#0a1628",
            "icons": [
                {
                    "src": app.get_asset_url("logo-sira_4.png"),
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "any maskable",
                }
            ],
        }
    )


clientside_callback(
    """
    function(n) {
        const d = window.__siraGeoLocateResult;
        if (!d) {
            return [
                window.dash_clientside.no_update,
                window.dash_clientside.no_update,
                window.dash_clientside.no_update,
                window.dash_clientside.no_update,
                window.dash_clientside.no_update,
            ];
        }
        window.__siraGeoLocateResult = null;
        return [
            d.provincia_id,
            d.municipio_id,
            d.localidad_id,
            {
                provincia_id: d.provincia_id,
                municipio_id: d.municipio_id,
                localidad_id: d.localidad_id,
                provincia: d.provincia,
                municipio: d.municipio,
                localidad: d.localidad,
            },
            true,
        ];
    }
    """,
    Output("geo-provincia", "value"),
    Output("geo-municipio", "value"),
    Output("geo-localidad", "value"),
    Output("geo-store", "data", allow_duplicate=True),
    Output("geo-locate-poll", "disabled", allow_duplicate=True),
    Input("geo-locate-poll", "n_intervals"),
    prevent_initial_call=True,
)


clientside_callback(
    """
    function(geo) {
        const el = document.getElementById('push-geo');
        if (el && geo) {
            el.dataset.provinciaId = geo.provincia_id || '';
            el.dataset.municipioId = geo.municipio_id || '';
            el.dataset.localidadId = geo.localidad_id || '';
            el.dataset.municipio = geo.municipio || '';
            el.dispatchEvent(new CustomEvent('sira-geo-changed'));
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output("push-geo", "children"),
    Input("geo-store", "data"),
)
