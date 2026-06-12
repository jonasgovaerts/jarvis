from fastapi import FastAPI

from gateway.config import settings


def create_app() -> FastAPI:
    app = FastAPI(title="jarvis-gateway")

    @app.get("/api/healthz")
    async def healthz() -> dict:
        return {"status": "ok", "service": settings().service_name}

    @app.get("/api/readyz")
    async def readyz() -> dict:
        # Will gate on NATS connectivity + first K8s list once those land.
        return {"status": "ok"}

    return app


app = create_app()
