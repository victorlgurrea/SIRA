"""Entry point uvicorn — implementación en sira.api.server."""
from sira.api.server import app

__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn

    from sira.config.settings import API_HOST, API_PORT

    uvicorn.run("sira.api.server:app", host=API_HOST, port=API_PORT)
