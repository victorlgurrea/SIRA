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
    ALLOW_DATA_REFRESH,
    API_HOST,
    API_KEY,
    API_PORT,
    CORS_ORIGINS,
    CRON_SECRET,
    ENABLE_API_DOCS,
    RATE_LIMIT_SEC,
)
from core import read_dashboard
from ingesta import ejecutar_ingesta
from push_web import add_subscription, notify_new_alerts, remove_subscription, send_test_push, vapid_enabled, vapid_public_key
from push_web import debug_aemet_matches, debug_push_state

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


class DebugAemetIn(BaseModel):
    provincia_id: str | None = None
    municipio_id: str | None = None
    localidad_id: str | None = None


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        return response


app.add_middleware(SecurityHeadersMiddleware)


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


@app.get("/api/dashboard")
def dashboard():
    return read_dashboard()


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api_server:app", host=API_HOST, port=API_PORT)
