"""API REST local — consulta de datos y actualización opcional."""
from __future__ import annotations

import secrets
import time
from collections import defaultdict

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from config import (
    ALLOW_DATA_REFRESH,
    API_HOST,
    API_KEY,
    API_PORT,
    CORS_ORIGINS,
    ENABLE_API_DOCS,
    RATE_LIMIT_SEC,
)
from core import read_dashboard
from ingesta import ejecutar_ingesta

app = FastAPI(title="SIRA API", docs_url="/docs" if ENABLE_API_DOCS else None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key"],
    allow_credentials=False,
)
_last_post: dict[str, float] = defaultdict(float)


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
    return {"ok": True, "generado_en": read_dashboard().get("generado_en")}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api_server:app", host=API_HOST, port=API_PORT)
