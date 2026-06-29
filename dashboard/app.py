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

from components import bloque, card, card_doble, card_sismos_combinada, dir_compass, mag_con_riesgo, meteo_ahora, riesgo_meteo_panel
from config import (  # noqa: E402
    AEMET_API_KEY,
    AEMET_MUNICIPIO,
    ALLOW_DATA_REFRESH,
    API_BASE_URL,
    API_KEY,
    DASHBOARD_HOST,
    DASHBOARD_PORT,
    DASHBOARD_REFRESH_MS,
    DASHBOARD_REFRESH_MIN,
    DATA_FILE,
    INCENDIO_MAP_MAX,
    INCENDIO_RADIO_LOCAL_KM,
    INGESTA_INTERVAL_MIN,
    MARES,
    MAPA,
    RIESGO_METEO_HORAS,
    ZONA,
)
from core import read_dashboard  # noqa: E402
from geo_es import coords_observacion, localidades, municipio_por_id, municipios, opciones, provincia_de_municipio, provincias
from geo_ui import selector_geo
from meteo_live import meteo_localidad
from aemet_alerts import alerta_coincide_zona, alerta_firma, deduplicar_alertas, fetch_active_alerts
from sismos import circle_disk_polygon, circle_perimeter, enriquecer_local
from incendios import enriquecer_local as enriquecer_incendio_local
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
        <link rel="stylesheet" href="/assets/sira.css?v=26">
        <link rel="icon" href="/assets/logo-sira_4.png?v=8" type="image/png">
        <link rel="manifest" href="/manifest.webmanifest">
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


def _default_geo() -> dict:
    muni = municipio_por_id(_DEFAULT_MUNI)
    prov = next((p for p in provincias() if p["id"] == _DEFAULT_PROV), None)
    loc = _locs[0] if _locs else None
    return {
        "provincia_id": _DEFAULT_PROV,
        "provincia": prov["nombre"] if prov else None,
        "municipio_id": _DEFAULT_MUNI,
        "municipio": muni["nombre"] if muni else None,
        "localidad_id": loc["id"] if loc else None,
        "localidad": loc["nombre"] if loc else None,
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

    return {
        "provincia_id": pid,
        "provincia": prov["nombre"] if prov else geo.get("provincia"),
        "municipio_id": muni_id,
        "municipio": muni["nombre"] if muni else geo.get("municipio"),
        "localidad_id": loc["id"] if loc else geo.get("localidad_id"),
        "localidad": loc["nombre"] if loc else geo.get("localidad"),
    }

_BTN_CLASS = "sira-btn-refresh" + ("" if ALLOW_DATA_REFRESH else " sira-btn-refresh--hidden")

app.layout = html.Div(className="sira-page", children=[
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
            selector_geo(_DEFAULT_PROV, _DEFAULT_MUNI, _DEFAULT_LOC),
            html.Div(className="sira-toolbar", children=[
                html.Div(className="sira-ts-wrap", children=[
                    html.Span(id="ts", className="sira-ts"),
                        html.Span(
                            f" · pantalla cada {DASHBOARD_REFRESH_MIN} min · datos cada {INGESTA_INTERVAL_MIN} min",
                            className="sira-ts-hint",
                        ),
                ]),
                html.Button("Actualizar", id="btn", n_clicks=0, className=_BTN_CLASS),
                html.Button("Activar notificaciones", id="push-btn", n_clicks=0, className="sira-btn-push"),
                html.Span("Push: desactivado", id="push-status", className="sira-push-status"),
            ]),
            html.Div(id="cards", className="sira-cards"),
            html.Div(className="sira-charts", children=[
                html.Div(className="sira-charts-row", children=[
                    bloque(
                        "mapa", "Mapa de riesgos — España",
                        f"Sismos M≥{ZONA['magnitud_min']} · incendios activos (solo España) · círculos = zona perceptible.",
                        map_chart=True, accent=C_ORANGE,
                    ),
                    bloque(
                        "lluvia", "Previsión de lluvia",
                        "Según la localidad seleccionada · AEMET o Open-Meteo.",
                        accent=C_TEAL,
                    ),
                ]),
                html.Div(className="sira-charts-row sira-charts-row--3", children=[
                    bloque(
                        "sst_med", "SST — Mediterráneo",
                        f"Temperatura superficial · {MARES['MEDITERRÁNEO']['punto']}.",
                        accent=C_ORANGE,
                    ),
                    bloque(
                        "sst_cant", "SST — Cantábrico",
                        f"Temperatura superficial · {MARES['CANTÁBRICO']['punto']}.",
                        accent=C_GREEN,
                    ),
                    bloque(
                        "sst_atl", "SST — Atlántico",
                        f"Temperatura superficial · {MARES['ATLÁNTICO']['punto']}.",
                        accent=C_CYAN,
                    ),
                ]),
                html.Div(className="sira-charts-row sira-charts-row--3", children=[
                    bloque(
                        "cor_med", "Corrientes — Mediterráneo",
                        f"Velocidad y dirección · {MARES['MEDITERRÁNEO']['punto']}.",
                        accent=C_ORANGE,
                    ),
                    bloque(
                        "cor_cant", "Corrientes — Cantábrico",
                        f"Velocidad y dirección · {MARES['CANTÁBRICO']['punto']}.",
                        accent=C_GREEN,
                    ),
                    bloque(
                        "cor_atl", "Corrientes — Atlántico",
                        f"Velocidad y dirección · {MARES['ATLÁNTICO']['punto']}.",
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
    local = list(d.get("meteo_alertas_test", [])) if isinstance(d.get("meteo_alertas_test"), list) else []
    live = list(d.get("meteo_alertas_live", [])) if isinstance(d.get("meteo_alertas_live"), list) else []
    if not live and AEMET_API_KEY:
        try:
            live = fetch_active_alerts(AEMET_API_KEY)
        except Exception:
            live = []
    return [*local, *live]


def _alertas_meteo_locales(geo: dict, d: dict) -> list[dict]:
    geo = _geo_resuelto(geo)
    filtradas = [
        a for a in _alertas_meteo_fuente(d)
        if alerta_coincide_zona(
            a,
            provincia_id=geo.get("provincia_id"),
            municipio_id=geo.get("municipio_id"),
            provincia=geo.get("provincia"),
            municipio=geo.get("municipio"),
        )
    ]
    return deduplicar_alertas(filtradas)


def _data_refresh_token(d: dict) -> str:
    firmas = sorted(
        "|".join(alerta_firma(a))
        for a in _alertas_meteo_fuente(d)
        if isinstance(a, dict)
    )
    return (
        f"{d.get('generado_en', '—')}|{len(d.get('sismos', []))}|{len(d.get('incendios', []))}"
        f"|{'|'.join(firmas)}|{bool(d.get('sismo_prueba_activo'))}"
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
        f"Probabilidad según AEMET Meteoalerta y predicción horaria ({h} h). "
        "El índice combinado es orientativo.",
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
    show_legend: bool = True,
) -> None:
    """Disco + borde del radio perceptible; pulso interior vía pulse-map.js."""
    if rows.empty:
        return
    radios = (
        rows["radio_perceptible_km"].tolist()
        if "radio_perceptible_km" in rows.columns
        else [120.0] * len(rows)
    )
    border_rgb = "220, 38, 38"
    for idx, row in enumerate(rows.itertuples(index=False)):
        r = float(radios[idx]) if idx < len(radios) else 120.0
        lat0 = float(row.lat)
        lon0 = float(row.lon)
        mag = float(getattr(row, "magnitud", 0) or 0)
        r0 = max(r * 0.06, 3.0)
        lat_fill, lon_fill = circle_disk_polygon(lat0, lon0, r0)
        lat_ring, lon_ring = circle_perimeter(lat0, lon0, r0)
        pulse_meta = {
            "center_lat": lat0,
            "center_lon": lon0,
            "radius_km": r,
            "period_ms": period_ms,
            "fill_rgb": fill_rgb,
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
                hovertemplate=(
                    f"Zona perceptible (hasta ~{r:.0f} km)<br>"
                    f"Mag {mag:.1f} · epicentro"
                    "<extra></extra>"
                ),
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
                meta={**pulse_meta, "pulse": "grow", "part": "border", "radius_fraction": 1.0, "border_rgb": border_rgb},
            )
        )


def _geo_layout(fig: go.Figure) -> None:
    fig.update_geos(
        scope="europe",
        projection_type="mercator",
        center=dict(lat=MAPA["lat_centro"], lon=MAPA["lon_centro"]),
        projection_scale=MAPA["projection_scale"],
        lataxis_range=[MAPA["lat_min"], MAPA["lat_max"]],
        lonaxis_range=[MAPA["lon_min"], MAPA["lon_max"]],
        showland=True, landcolor=C_NAVY,
        showocean=True, oceancolor="#1e4976",
        showcountries=True, countrycolor="#1e4976", coastlinecolor="#94a3b8",
    )
    fig.update_layout(
        margin=dict(t=10, b=0, l=0, r=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        autosize=True,
        uirevision="sira-mapa",
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
    lat_fill, lon_fill = circle_disk_polygon(lat, lon, r_draw)
    lat_ring, lon_ring = circle_perimeter(lat, lon, r_draw)
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


def _fig_mapa(
    sismos: list,
    incendios: list | None = None,
    lat_obs: float | None = None,
    lon_obs: float | None = None,
    obs_nombre: str = "",
) -> go.Figure:
    fig = go.Figure()
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
        df_per = df[df["perceptible_local"].fillna(False)]
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
                "%{text}<br>"
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
        _add_circulos_perceptibles(
            fig,
            hoy_df,
            legend_name="Zona perceptible (hoy)",
            legendgroup="hoy",
            period_ms=1600,
        )

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
    for lat, lon, name, color in (
        (MAPA["lat_centro"], MAPA["lon_centro"], MAPA["ciudad_centro"], "gold"),
        (ZONA["lat_ref"], ZONA["lon_ref"], ZONA["ciudad_ref"], C_CYAN),
    ):
        fig.add_trace(go.Scattergeo(
            lat=[lat], lon=[lon], mode="markers+text", text=[name], showlegend=False,
            marker=dict(size=10, color=color, symbol="star"),
        ))
    _geo_layout(fig)
    fig.update_layout(legend=dict(title="Alerta", orientation="h", yanchor="bottom", y=1.02, x=0))
    return fig


def _fig_corrientes(serie: list, uirev: str) -> go.Figure:
    fig = go.Figure()
    dir_txt = "—"
    ult_txt = "Última: — m/s"
    if serie:
        s = pd.DataFrame(serie)
        s["timestamp"] = pd.to_datetime(s["timestamp"], errors="coerce")
        fig.add_trace(go.Scatter(
            x=s["timestamp"], y=s["corriente_vel_ms"],
            mode="lines", name="m/s", line=dict(color=C_GREEN),
        ))
        vel = s["corriente_vel_ms"].dropna()
        if not vel.empty:
            ult_txt = f"Última: {float(vel.iloc[-1]):.2f} m/s"
        if s["corriente_dir_grados"].notna().any():
            dir_txt = dir_compass(s["corriente_dir_grados"].dropna().iloc[-1])
    fig.update_layout(
        margin=dict(t=28, b=0, l=0, r=0),
        autosize=True,
        yaxis_title="m/s",
        uirevision=uirev,
        annotations=[
            dict(
                text=f"Dirección: {dir_txt}",
                xref="paper", yref="paper", x=0, y=1.12,
                showarrow=False, font=dict(color=C_GREEN, size=11),
            ),
            dict(
                text=ult_txt,
                xref="paper", yref="paper", x=1, y=1.12,
                xanchor="right",
                showarrow=False, font=dict(color=C_TEXT, size=11),
            ),
        ],
        **PLOTLY_BG,
    )
    return fig


def _stats_region(sismos: list) -> dict[str, int]:
    reg: dict[str, int] = {}
    for s in sismos:
        r = s.get("region", "")
        reg[r] = reg.get(r, 0) + 1
    return reg


def _fig_linea(serie: list, campo: str, color: str, unidad: str, uirev: str) -> go.Figure:
    fig = go.Figure()
    ult_txt = f"Última: — {unidad}"
    if serie:
        s = pd.DataFrame(serie)
        s["timestamp"] = pd.to_datetime(s["timestamp"], errors="coerce")
        fig.add_trace(go.Scatter(x=s["timestamp"], y=s[campo], mode="lines", line=dict(color=color)))
        vals = s[campo].dropna()
        if not vals.empty:
            ult_txt = f"Última: {float(vals.iloc[-1]):.2f} {unidad}"
    fig.update_layout(
        margin=dict(t=28, b=0, l=0, r=0),
        autosize=True,
        yaxis_title=unidad,
        uirevision=uirev,
        annotations=[dict(
            text=ult_txt,
            xref="paper", yref="paper",
            x=1, y=1.12,
            xanchor="right",
            showarrow=False,
            font=dict(color=C_TEXT, size=11),
        )],
        **PLOTLY_BG,
    )
    return fig


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
    fig.update_layout(
        margin=dict(t=10, b=0, l=0, r=0),
        autosize=True,
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
    return {
        "provincia_id": provincia_id,
        "provincia": prov["nombre"] if prov else None,
        "municipio_id": municipio_id,
        "municipio": muni["nombre"] if muni else None,
        "localidad_id": localidad_id,
        "localidad": loc["nombre"] if loc else None,
    }


@callback(
    Output("cards", "children"), Output("ts", "children"), Output("data-ts-store", "data"),
    Output("mapa", "figure"), Output("lluvia", "figure"),
    Output("sst_med", "figure"), Output("sst_cant", "figure"), Output("sst_atl", "figure"),
    Output("cor_med", "figure"), Output("cor_cant", "figure"), Output("cor_atl", "figure"),
    Input("tick", "n_intervals"), Input("btn", "n_clicks"), Input("geo-store", "data"),
    State("data-ts-store", "data"),
)
def refresh(n_intervals, clicks, geo, last_ts):
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
    ts_raw = d.get("generado_en", "—")
    refresh_token = _data_refresh_token(d)
    if ctx.triggered_id == "tick" and n_intervals and last_ts == refresh_token:
        raise PreventUpdate

    geo = _geo_resuelto(geo)
    muni_id = geo.get("municipio_id") or _DEFAULT_MUNI
    localidad = geo.get("localidad") or ZONA["ciudad_ref"]
    lat_obs, lon_obs, _ = coords_observacion(muni_id, geo.get("localidad_id"))

    sismos_all = d.get("sismos", [])
    sismos_mapa = [enriquecer_local(s, lat_obs, lon_obs) for s in sismos_all]
    sismos = [s for s in sismos_mapa if s.get("perceptible_local")]
    incendios_all = d.get("incendios", [])
    incendios_mapa = [enriquecer_incendio_local(i, lat_obs, lon_obs) for i in incendios_all]
    incendios_local = [i for i in incendios_mapa if i.get("afecta_local")]
    oce = d.get("oceanografia", {})
    met = meteo_localidad(muni_id, localidad)
    alertas_meteo = _alertas_meteo_locales(geo, d)

    mag_max = max((s["magnitud"] for s in sismos), default=0)
    sismo_max = _sismo_mag_max(sismos, mag_max)
    nivel_max = sismo_max.get("nivel_local", sismo_max.get("nivel_alerta")) if sismo_max else None
    res_met = met.get("resumen", {})

    loc_label = f"{localidad}, {geo.get('municipio') or ''}".strip(", ")

    cards = [
        card_sismos_combinada(
            len(sismos_all),
            len(sismos),
            localidad,
            float(mag_max),
            nivel_max,
            _detalle_sismo(sismo_max),
            f"M≥{ZONA['magnitud_min']}, últimos {ZONA['dias_atras']} días · mapa: perceptibles + incendios España.",
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
            "Lluvia 24h", f"{res_met.get('precip_prox_24h_mm', '—')} mm",
            f"Prob. máx. {res_met.get('prob_max_pct', '—')}% · {met.get('fuente', '—')}",
            loc_label,
            accent=C_TEAL,
        ),
        card(
            "Tiempo ahora",
            meteo_ahora(res_met),
            f"Según {met.get('fuente', '—')} · {loc_label}",
            "Estado del cielo, temperatura y viento en la localidad seleccionada.",
            accent=C_CYAN,
        ),
    ]
    riesgo_meteo = calcular_riesgo_meteo(alertas_meteo, met, horas=RIESGO_METEO_HORAS)
    cards.append(_riesgo_meteo_card(riesgo_meteo))
    ts = d.get("generado_en", "—")
    try:
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M UTC")
    except (ValueError, AttributeError):
        pass
    if d.get("sismo_prueba_activo"):
        ts = f"{ts} · Sismo de prueba en mapa"

    oce_med = _bloque_oce(oce, "MEDITERRÁNEO")
    oce_cant = _bloque_oce(oce, "CANTÁBRICO")
    oce_atl = _bloque_oce(oce, "ATLÁNTICO")

    return (
        cards, f"Actualizado: {ts}", refresh_token,
        _fig_mapa(sismos_mapa, incendios_mapa, lat_obs, lon_obs, localidad),
        _fig_lluvia(met.get("serie_horaria", [])),
        _fig_linea(oce_med.get("serie_horaria", []), "sst_c", C_ORANGE, "°C", "sira-sst-med"),
        _fig_linea(oce_cant.get("serie_horaria", []), "sst_c", C_GREEN, "°C", "sira-sst-cant"),
        _fig_linea(oce_atl.get("serie_horaria", []), "sst_c", C_CYAN, "°C", "sira-sst-atl"),
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
