"""Rutas Flask auxiliares del dashboard (PWA, estado, manifest)."""
from __future__ import annotations

from pathlib import Path

from flask import Response, jsonify, redirect, request, send_from_directory

from sira.config.settings import API_BASE_URL
from sira.infrastructure.http.client import fmt_ingesta_local, read_dashboard
from sira.infrastructure.persistence.sqlite import count_subscriptions

# Stub cuando Dash pide async-plotlyjs.js (en PRO esa ruta del suite devuelve 500).
_ASYNC_PLOTLYJS_STUB = """
(function (root) {
  var P = root.Plotly;
  if (typeof define === "function" && define.amd) {
    define(function () { return P; });
  } else if (typeof module === "object" && module.exports) {
    module.exports = P;
  } else {
    root.PlotlyAsync = P;
  }
})(typeof self !== "undefined" ? self : this);
"""

_FUENTE_ETIQUETAS = {
    "usgs": "USGS + EMSC (sismos)",
    "aemet_meteo": "AEMET meteo",
    "termico_ccaa": "Térmico CCAA (ingesta)",
    "aemet_cap": "AEMET CAP",
    "open_meteo_marine": "Open-Meteo marine",
    "cmems_sst_med": "CMEMS SST Mediterráneo",
    "open_meteo_weather": "Open-Meteo weather",
    "firms": "NASA FIRMS",
    "embals_es": "embals.es",
    "saih_chj": "SAIH CHJ",
    "saih_che": "SAIH Ebro",
    "saih_chs": "SAIH Segura",
}

_FUENTE_DESCRIPCIONES = {
    "usgs": "Sismos recientes en España y entorno (USGS + EMSC; magnitud, epicentro, profundidad, alerta tsunami USGS).",
    "aemet_meteo": "Predicción horaria municipal AEMET (lluvia, probabilidad de precipitación, tiempo actual).",
    "termico_ccaa": "Temperatura máxima prevista 24 h por provincia/CCAA (alimenta el mapa de riesgos).",
    "aemet_cap": "Avisos Meteoalerta CAP por zona (temperatura, viento, lluvia, costa, tormentas, etc.).",
    "open_meteo_marine": "Temperatura superficial del mar y corrientes (Mediterráneo, Cantábrico, Atlántico).",
    "cmems_sst_med": "Cuadrícula SST satélite del Mediterráneo occidental (Copernicus Marine L4).",
    "open_meteo_weather": "Previsión horaria de precipitación (respaldo cuando AEMET no está disponible).",
    "firms": "Puntos de calor e incendios activos detectados por satélite en territorio español.",
    "embals_es": "Niveles, capacidad y riesgo hidrológico de embalses (cuencas Júcar, Segura y Ebro).",
    "saih_chj": "Caudales y estaciones de aforo en tiempo casi real (SAIH, Confederación Hidrográfica del Júcar).",
    "saih_che": "Aforos SAIH cuenca del Ebro (CHE). Pendiente de API pública MITECO.",
    "saih_chs": "Caudales y niveles en tiempo casi real (SAIH, Confederación Hidrográfica del Segura).",
}

_ANDROID_SHA256_DEBUG = (
    "30:20:B7:AC:BD:FB:CF:A4:90:77:A2:20:6F:F0:73:10:"
    "B3:A0:A7:87:78:8E:E0:48:3F:B1:50:B8:D9:0E:F8:D4"
)


def status_snapshot() -> dict:
    """Lee estado desde API; fallback local / snapshot si no responde. Nunca lanza."""
    empty = {
        "generado_en": "—",
        "fuentes_estado": {},
        "suscripciones_push": 0,
        "ingesta": {"running": False, "started_at": None, "finished_at": None, "last_error": None},
        "ok": False,
    }
    try:
        from sira.infrastructure.http.dashboard_fetch import (
            _payload_score,
            ensure_dashboard_on_disk,
            fetch_status_api,
        )

        # Primero disco/snapshot: en PRO la API suele estar vacía tras hibernar.
        data = ensure_dashboard_on_disk()
        payload = fetch_status_api(API_BASE_URL)

        local_score = _payload_score(data) if isinstance(data, dict) else 0
        api_fuentes = (
            payload.get("fuentes_estado")
            if isinstance(payload, dict) and isinstance(payload.get("fuentes_estado"), dict)
            else {}
        )
        api_fuentes_ok = sum(
            1 for v in api_fuentes.values() if isinstance(v, dict) and v.get("ok")
        )

        if isinstance(payload, dict) and payload.get("generado_en") and api_fuentes_ok > 0 and local_score == 0:
            return payload

        if isinstance(data, dict) and data.get("generado_en") and local_score > 0:
            out = {
                "generado_en": data.get("generado_en"),
                "fuentes_estado": (
                    data.get("fuentes_estado") if isinstance(data.get("fuentes_estado"), dict) else {}
                ),
                "suscripciones_push": count_subscriptions(),
                "ingesta": (
                    payload.get("ingesta")
                    if isinstance(payload, dict) and isinstance(payload.get("ingesta"), dict)
                    else {"running": False, "started_at": None, "finished_at": None, "last_error": None}
                ),
                "ok": True,
            }
            return out

        if isinstance(payload, dict) and api_fuentes_ok > 0:
            return payload

        if isinstance(data, dict) and data.get("generado_en"):
            return {
                "generado_en": data.get("generado_en"),
                "fuentes_estado": (
                    data.get("fuentes_estado") if isinstance(data.get("fuentes_estado"), dict) else {}
                ),
                "suscripciones_push": count_subscriptions(),
                "ingesta": {"running": False, "started_at": None, "finished_at": None, "last_error": None},
                "ok": local_score > 0,
            }

        return {
            "generado_en": "—",
            "fuentes_estado": {},
            "suscripciones_push": count_subscriptions(),
            "ingesta": {"running": False, "started_at": None, "finished_at": None, "last_error": None},
            "ok": False,
        }
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).exception("status_snapshot falló")
        try:
            data = read_dashboard()
            empty["generado_en"] = data.get("generado_en", "—") if isinstance(data, dict) else "—"
            empty["fuentes_estado"] = (
                data.get("fuentes_estado")
                if isinstance(data, dict) and isinstance(data.get("fuentes_estado"), dict)
                else {}
            )
            empty["ok"] = bool(isinstance(data, dict) and data.get("generado_en"))
            empty["suscripciones_push"] = count_subscriptions()
        except Exception:  # noqa: BLE001
            pass
        return empty


def register_routes(server, dash_app, assets_path: Path, plotly_cdn: str | None = None) -> None:
    """Registra rutas Flask no gestionadas por Dash."""

    cdn = (plotly_cdn or "").strip()

    @server.before_request
    def _fix_plotly_suite_routes():
        """En Render Free, dash/dcc/plotly*.js responde 500 y la UI se queda en Loading..."""
        path = request.path or ""
        if not path.startswith("/_dash-component-suites/"):
            return None
        if path.endswith("/async-plotlyjs.js"):
            return Response(
                _ASYNC_PLOTLYJS_STUB,
                mimetype="application/javascript",
                headers={"Cache-Control": "public, max-age=86400"},
            )
        if cdn and path.endswith("/plotly.min.js") and "/dash/dcc/" in path:
            return redirect(cdn, code=302)
        return None

    @server.route("/sw.js")
    def _service_worker():
        resp = send_from_directory(str(assets_path), "sw.js")
        resp.headers["Service-Worker-Allowed"] = "/"
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp

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

    @server.route("/status")
    def _status_page():
        try:
            data = status_snapshot()
        except Exception:  # noqa: BLE001
            data = {
                "generado_en": "—",
                "fuentes_estado": {},
                "suscripciones_push": 0,
                "ingesta": {},
                "ok": False,
            }
        fuentes = data.get("fuentes_estado") if isinstance(data.get("fuentes_estado"), dict) else {}
        generado = fmt_ingesta_local(data.get("generado_en"))
        n_push = data.get("suscripciones_push", 0)
        ingesta = data.get("ingesta") if isinstance(data.get("ingesta"), dict) else {}
        ingesta_running = bool(ingesta.get("running"))
        ingesta_estado = "En curso" if ingesta_running else "Reposo"
        ingesta_ini = fmt_ingesta_local(ingesta.get("started_at"))
        ingesta_fin = fmt_ingesta_local(ingesta.get("finished_at"))
        ingesta_err = ingesta.get("last_error") or "—"
        filas = []
        for clave, etiqueta in _FUENTE_ETIQUETAS.items():
            raw = fuentes.get(clave, {})
            info = raw if isinstance(raw, dict) else {}
            desc = _FUENTE_DESCRIPCIONES.get(clave, "—")
            ok = info.get("ok")
            if info.get("omitido"):
                estado = '<span class="sira-status-warn">omitido</span>'
            elif clave == "saih_che" and ok and int(info.get("registros") or 0) == 0:
                estado = (
                    '<span class="sira-status-warn">cobertura parcial</span> '
                    '<span class="sira-status-meta">(sin API pública estable)</span>'
                )
            elif ok:
                n = info.get("registros", "—")
                estado = f'<span class="sira-status-ok">OK</span> <span class="sira-status-meta">({n} registros)</span>'
            elif not info:
                # Sin entrada aún (arranque / ingesta en curso): no es un fallo real.
                if ingesta_running:
                    estado = '<span class="sira-status-warn">pendiente</span> <span class="sira-status-meta">(ingesta en curso)</span>'
                else:
                    estado = '<span class="sira-status-warn">sin datos</span>'
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
  <meta name="theme-color" content="#0a1628">
  <script src="/assets/theme.js"></script>
  <link rel="stylesheet" href="/assets/sira.css?v=36">
</head>
<body class="sira-page sira-status-page">
  <main class="sira-main">
    <div class="sira-container">
      <h1 class="sira-title">Estado del sistema</h1>
      <p class="sira-status-ts">Última ingesta: <strong>{generado}</strong> <span class="sira-ts-badge">Hora local</span></p>
      <p class="sira-status-ts">Estado ingesta: <strong>{ingesta_estado}</strong> · Inicio: <strong>{ingesta_ini}</strong> · Fin: <strong>{ingesta_fin}</strong></p>
      <p class="sira-status-ts">Último error ingesta: <strong>{ingesta_err}</strong></p>
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
                        "src": dash_app.get_asset_url("logo-sira_4.png"),
                        "sizes": "512x512",
                        "type": "image/png",
                        "purpose": "any maskable",
                    }
                ],
            }
        )
