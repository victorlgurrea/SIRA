"""API REST local."""
from __future__ import annotations

import time
from collections import defaultdict

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from config import API_HOST, API_KEY, API_PORT, CORS_ORIGINS, ENABLE_API_DOCS, RATE_LIMIT_SEC
from core import read_dashboard
from ingesta import ejecutar_ingesta

app = FastAPI(title="SIRA API", docs_url="/docs" if ENABLE_API_DOCS else None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["GET", "POST"], allow_headers=["X-API-Key"])
_last_post: dict[str, float] = defaultdict(float)


@app.get("/api/dashboard")
def dashboard():
    return read_dashboard()


@app.post("/api/actualizar")
def actualizar(request: Request, x_api_key: str | None = Header(default=None)):
    if not API_KEY:
        raise HTTPException(503, "API_KEY no configurada")
    if x_api_key != API_KEY:
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
