"""API REST local — consulta de datos y actualización opcional."""
from __future__ import annotations

import logging
import secrets
import time
from collections import defaultdict

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from config import (
    AEMET_MUNICIPIO,
    ALLOW_DATA_REFRESH,
    API_HOST,
    API_KEY,
    API_PORT,
    CORS_ORIGINS,
    CRON_SECRET,
    ENABLE_API_DOCS,
    HISTORIAL_DIAS_DEFAULT,
    RATE_LIMIT_SEC,
)
from core import read_dashboard
from db import count_subscriptions, get_historial_municipio, migrar_desde_json
from geo_es import municipio_mas_cercano, municipio_por_id, provincia_de_municipio, provincias
from ingesta import ejecutar_ingesta
from meteo_live import meteo_localidad
from push_web import add_subscription, notify_new_alerts, remove_subscription, send_test_meteo_push, send_test_push, vapid_enabled, vapid_public_key
from push_web import debug_aemet_matches, debug_push_state
from test_meteo_alerts import save_test_alert

log = logging.getLogger(__name__)

app = FastAPI(title="SIRA API", docs_url="/docs" if ENABLE_API_DOCS else None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "X-Cron-Secret", "Content-Type"],
    allow_credentials=False,
)
_last_post: dict[str, float] = defaultdict(float)


class SubscriptionIn(BaseModel):
    endpoint: str
    keys: dict
    provincia_id: str | None = None
    municipio_id: str | None = None
    localidad_id: str | None = None
    alertas: list[str] | None = None


class UnsubscribeIn(BaseModel):
    endpoint: str


class TestPushIn(BaseModel):
    title: str | None = None
    body: str | None = None
    url: str | None = None
    tag: str | None = None
    renotify: bool = True
    solo_municipio_id: str | None = None
    mostrar_en_mapa: bool = True
    magnitud: float | None = None
    lat: float | None = None
    lon: float | None = None
    profundidad: float | None = None
    lugar: str | None = None
    overlay_minutos: int = 30
    simular_real: bool = True
    tsunami: bool = False


class DebugAemetIn(BaseModel):
    provincia_id: str | None = None
    municipio_id: str | None = None
    localidad_id: str | None = None


class TestMeteoIn(BaseModel):
    tipo: str = "AT"  # AT temperatura, VI viento, CO costero, PR lluvia...
    nivel: str = "naranja"  # amarillo|naranja|rojo
    parametro: str | None = None
    descripcion: str | None = None
    area_desc: str | None = None
    ttl_minutos: int = 30
    enviar_push: bool = True
    solo_municipio_id: str | None = None


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        return response


app.add_middleware(SecurityHeadersMiddleware)


@app.on_event("startup")
def _startup_migrar_json() -> None:
    try:
        migrar_desde_json()
    except Exception as exc:  # noqa: BLE001
        log.warning("Migración JSON→SQLite: %s", exc)


def _valid_api_key(provided: str | None) -> bool:
    if not API_KEY or not provided:
        return False
    return secrets.compare_digest(provided, API_KEY)


def _valid_push_test_auth(api_key: str | None, cron_secret: str | None) -> bool:
    if _valid_api_key(api_key):
        return True
    if CRON_SECRET and cron_secret and secrets.compare_digest(cron_secret, CRON_SECRET):
        return True
    return False


def _require_debug_auth(api_key: str | None, cron_secret: str | None) -> None:
    if not API_KEY and not CRON_SECRET:
        raise HTTPException(503, "API_KEY o CRON_SECRET no configurado en el servidor")
    if not _valid_push_test_auth(api_key, cron_secret):
        raise HTTPException(401, "No autorizado (X-API-Key o X-Cron-Secret inválido)")


def _meteo_test_defaults(municipio_id: str | None) -> tuple[str, str]:
    muni_id = str(municipio_id or AEMET_MUNICIPIO).zfill(5)
    muni = municipio_por_id(muni_id)
    prov_id = provincia_de_municipio(muni_id) or "46"
    prov_name = next((p.get("nombre") for p in provincias() if str(p.get("id")) == str(prov_id)), "Valencia")
    area = f"{muni.get('nombre') if muni else 'Valencia'} ({prov_name})"
    return muni_id, area


@app.get("/api/dashboard")
def dashboard():
    return read_dashboard()


@app.get("/api/status")
def status():
    data = read_dashboard()
    fuentes = data.get("fuentes_estado") if isinstance(data.get("fuentes_estado"), dict) else {}
    return {
        "generado_en": data.get("generado_en"),
        "fuentes_estado": fuentes,
        "suscripciones_push": count_subscriptions(),
        "ok": bool(data.get("generado_en")),
    }


@app.get("/api/historial/{municipio_id}")
def historial(municipio_id: str, dias: int = HISTORIAL_DIAS_DEFAULT):
    mid = str(municipio_id).zfill(5)
    muni = municipio_por_id(mid)
    if not muni:
        raise HTTPException(404, "Municipio no encontrado")
    dias = max(1, min(int(dias), 365))
    return {
        "municipio_id": mid,
        "municipio": muni.get("nombre"),
        "dias": dias,
        "serie": get_historial_municipio(mid, dias),
    }


@app.get("/api/meteo/{municipio_id}")
def meteo_municipio(municipio_id: str, localidad: str | None = None):
    """Meteo horaria AEMET (o Open-Meteo) para el municipio seleccionado."""
    mid = str(municipio_id).zfill(5)
    muni = municipio_por_id(mid)
    if not muni:
        raise HTTPException(404, "Municipio no encontrado")
    nombre_loc = (localidad or "").strip() or None
    return meteo_localidad(mid, nombre_loc)


@app.get("/api/geo/municipio-cercano")
def geo_municipio_cercano(lat: float, lon: float):
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise HTTPException(400, "Coordenadas inválidas")
    res = municipio_mas_cercano(lat, lon)
    if not res:
        raise HTTPException(404, "Sin municipios en catálogo geo")
    locs = []
    from geo_es import localidades

    locs = localidades(res["municipio_id"])
    return {
        **res,
        "localidad_id": locs[0]["id"] if locs else res["municipio_id"],
        "localidad": locs[0]["nombre"] if locs else res["municipio"],
    }


@app.post("/api/actualizar")
def actualizar(request: Request, x_api_key: str | None = Header(default=None)):
    if not ALLOW_DATA_REFRESH:
        raise HTTPException(403, "Actualización deshabilitada (modo solo consulta)")
    if not API_KEY:
        raise HTTPException(503, "API_KEY no configurada")
    if not _valid_api_key(x_api_key):
        raise HTTPException(401, "API key inválida")
    client = request.client.host if request.client else "unknown"
    if time.monotonic() - _last_post[client] < RATE_LIMIT_SEC:
        raise HTTPException(429, f"Espera {RATE_LIMIT_SEC}s")
    _last_post[client] = time.monotonic()
    ejecutar_ingesta()
    n = notify_new_alerts(CORS_ORIGINS[0] if CORS_ORIGINS else "https://sira-dashboard.onrender.com")
    return {"ok": True, "generado_en": read_dashboard().get("generado_en"), "push_enviados": n}


@app.post("/api/cron/ingesta")
def cron_ingesta(x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret")):
    """Ingesta programada (GitHub Actions u otro cron). Requiere CRON_SECRET en el servidor."""
    if not CRON_SECRET:
        raise HTTPException(503, "CRON_SECRET no configurado")
    if not x_cron_secret or not secrets.compare_digest(x_cron_secret, CRON_SECRET):
        raise HTTPException(401, "No autorizado")
    ejecutar_ingesta()
    n = notify_new_alerts(CORS_ORIGINS[0] if CORS_ORIGINS else "https://sira-dashboard.onrender.com")
    return {"ok": True, "generado_en": read_dashboard().get("generado_en"), "push_enviados": n}


@app.get("/api/push/public-key")
def push_public_key():
    if not vapid_enabled():
        raise HTTPException(503, "Web Push no configurado")
    return {"public_key": vapid_public_key()}


@app.post("/api/push/subscribe")
def push_subscribe(sub: SubscriptionIn):
    n = add_subscription(sub.model_dump())
    return {"ok": True, "suscripciones": n}


@app.post("/api/push/unsubscribe")
def push_unsubscribe(payload: UnsubscribeIn):
    n = remove_subscription(payload.endpoint)
    return {"ok": True, "suscripciones": n}


@app.post("/api/push/test")
def push_test(
    payload: TestPushIn,
    x_api_key: str | None = Header(default=None),
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """Notificación de prueba (Postman). Requiere X-API-Key o X-Cron-Secret."""
    if not API_KEY and not CRON_SECRET:
        raise HTTPException(503, "API_KEY o CRON_SECRET no configurado en el servidor")
    if not _valid_push_test_auth(x_api_key, x_cron_secret):
        raise HTTPException(401, "No autorizado (X-API-Key o X-Cron-Secret inválido)")
    if not vapid_enabled():
        raise HTTPException(503, "Web Push no configurado")
    dashboard_url = CORS_ORIGINS[0] if CORS_ORIGINS else "https://sira-dashboard.onrender.com"
    try:
        result = send_test_push(
            dashboard_url,
            title=payload.title,
            body=payload.body,
            url=payload.url,
            tag=payload.tag or "sira-test-valencia",
            renotify=payload.renotify,
            solo_municipio_id=payload.solo_municipio_id,
            mostrar_en_mapa=payload.mostrar_en_mapa,
            magnitud=payload.magnitud,
            lat=payload.lat,
            lon=payload.lon,
            profundidad=payload.profundidad,
            lugar=payload.lugar,
            overlay_minutos=payload.overlay_minutos,
            simular_real=payload.simular_real,
            tsunami=payload.tsunami,
        )
    except Exception as exc:
        log.exception("push/test falló")
        raise HTTPException(500, f"Error interno al enviar push: {exc}") from exc
    if not result.get("ok"):
        raise HTTPException(404 if result.get("error") == "No hay suscripciones activas" else 503, result.get("error", "Envío fallido"))
    return result


@app.get("/api/debug/push")
def debug_push(
    x_api_key: str | None = Header(default=None),
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    _require_debug_auth(x_api_key, x_cron_secret)
    return debug_push_state()


@app.post("/api/debug/aemet")
def debug_aemet(
    payload: DebugAemetIn,
    x_api_key: str | None = Header(default=None),
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    _require_debug_auth(x_api_key, x_cron_secret)
    try:
        return debug_aemet_matches(
            provincia_id=payload.provincia_id,
            municipio_id=payload.municipio_id,
            localidad_id=payload.localidad_id,
        )
    except Exception as exc:
        log.exception("debug/aemet falló")
        raise HTTPException(500, f"Error interno al leer avisos AEMET: {exc}") from exc


@app.post("/api/meteo/test")
def meteo_test(
    payload: TestMeteoIn,
    x_api_key: str | None = Header(default=None),
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    _require_debug_auth(x_api_key, x_cron_secret)
    muni_id, area_default = _meteo_test_defaults(payload.solo_municipio_id)
    tipo = (payload.tipo or "AT").strip().upper()
    nivel = (payload.nivel or "naranja").strip().lower()
    names = {
        "AT": ("Temperatura máxima", "TA;Temperatura máxima;39 ºC"),
        "VI": ("Viento", "RM;Racha máxima;90 km/h"),
        "CO": ("Fenómeno costero", "CO;Oleaje;4 m"),
        "PR": ("Lluvia", "P1;Precipitación 1h;30 mm"),
        "TO": ("Tormenta", "TO;Tormenta;muy fuerte"),
    }
    desc, param_default = names.get(tipo, ("Fenómeno meteorológico", f"{tipo};Fenómeno;—"))
    alert = {
        "id": f"aemet-test-{tipo}-{int(time.time())}",
        "source": "AEMET",
        "level": nivel,
        "severity": {"amarillo": "moderate", "naranja": "severe", "rojo": "extreme"}.get(nivel, "severe"),
        "urgency": "expected",
        "certainty": "likely",
        "headline": f"Aviso de {desc} ({nivel})",
        "description": payload.descripcion or f"Prueba de aviso {desc} para validar widget y push.",
        "area_desc": payload.area_desc or area_default,
        "fenomeno": tipo,
        "fenomeno_desc": desc,
        "parametro": payload.parametro or param_default,
        "probabilidad": "40%-70%",
        "zona": f"test-{muni_id}",
        "icon": {"AT": "🌡️", "VI": "💨", "CO": "🌊", "PR": "🌧️", "TO": "⛈️"}.get(tipo, "⚠️"),
    }
    saved = save_test_alert(alert, ttl_min=payload.ttl_minutos)
    out = {"ok": True, "alerta": saved}
    if payload.enviar_push:
        if not vapid_enabled():
            out["push"] = {"ok": False, "error": "Web Push no configurado (VAPID)", "enviados": 0}
        else:
            dashboard_url = CORS_ORIGINS[0] if CORS_ORIGINS else "https://sira-dashboard.onrender.com"
            out["push"] = send_test_meteo_push(dashboard_url, saved)
    return out


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api_server:app", host=API_HOST, port=API_PORT)
