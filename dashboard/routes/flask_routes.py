"""Rutas Flask auxiliares del dashboard (PWA, estado, manifest)."""
from __future__ import annotations

from pathlib import Path

import requests
from flask import Response, jsonify, send_from_directory

from sira.config.settings import API_BASE_URL
from sira.infrastructure.http.client import fmt_ingesta_local, read_dashboard
from sira.infrastructure.persistence.sqlite import count_subscriptions

_FUENTE_ETIQUETAS = {
    "usgs": "USGS (sismos)",
    "aemet_meteo": "AEMET meteo",
    "termico_ccaa": "Térmico CCAA (ingesta)",
    "aemet_cap": "AEMET CAP",
    "open_meteo_marine": "Open-Meteo marine",
    "open_meteo_weather": "Open-Meteo weather",
    "firms": "NASA FIRMS",
    "embals_es": "embals.es",
    "saih_chj": "SAIH CHJ",
    "saih_che": "SAIH Ebro",
    "saih_chs": "SAIH Segura",
}

_FUENTE_DESCRIPCIONES = {
    "usgs": "Sismos recientes en España y entorno (magnitud, epicentro, profundidad, alerta tsunami USGS).",
    "aemet_meteo": "Predicción horaria municipal AEMET (lluvia, probabilidad de precipitación, tiempo actual).",
    "termico_ccaa": "Temperatura máxima prevista 24 h por provincia/CCAA (alimenta el mapa de riesgos).",
    "aemet_cap": "Avisos Meteoalerta CAP por zona (temperatura, viento, lluvia, costa, tormentas, etc.).",
    "open_meteo_marine": "Temperatura superficial del mar y corrientes (Mediterráneo, Cantábrico, Atlántico).",
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


def register_routes(server, dash_app, assets_path: Path) -> None:
    """Registra rutas Flask no gestionadas por Dash."""

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
        data = status_snapshot()
        fuentes = data.get("fuentes_estado") if isinstance(data.get("fuentes_estado"), dict) else {}
        generado = fmt_ingesta_local(data.get("generado_en"))
        n_push = data.get("suscripciones_push", 0)
        filas = []
        for clave, etiqueta in _FUENTE_ETIQUETAS.items():
            info = fuentes.get(clave, {})
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
