from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from gateway.api import chat, drafts, features, repos, tasks, workflows, ws
from gateway.config import settings
from gateway.events.fanout import run_history_consumer, run_ws_fanout
from gateway.k8s.watcher import run_watcher, seed_fixtures
from gateway.state import state
from jarvis_core import bus
from jarvis_core.db import create_engine_and_factory, init_models

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = settings()
    logging.basicConfig(level=cfg.log_level)
    background: list[asyncio.Task] = []

    state.engine, state.session_factory = create_engine_and_factory(cfg.database_url)
    await init_models(state.engine)

    if cfg.fake_k8s:
        log.warning("FAKE_K8S enabled — serving board fixtures")
        seed_fixtures(state.cache)
    else:
        background.append(asyncio.create_task(run_watcher(state.cache, cfg.workitem_namespace)))

    if cfg.nats_url:
        try:
            state.nc, state.js = await asyncio.wait_for(bus.connect(cfg.nats_url), timeout=10)
            background.append(asyncio.create_task(run_ws_fanout(state.nc, state.hub)))
            background.append(
                asyncio.create_task(run_history_consumer(state.js, state.session_factory))
            )
            log.info("NATS connected: %s", cfg.nats_url)
        except Exception:  # noqa: BLE001 - degrade: REST works, live updates don't
            log.exception("NATS unavailable; live updates disabled")
    else:
        log.warning("NATS_URL empty — live updates disabled")

    yield

    for task in background:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
    if state.nc is not None:
        with contextlib.suppress(Exception):
            await state.nc.drain()
    if state.engine is not None:
        await state.engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="jarvis-gateway", lifespan=lifespan)

    app.include_router(workflows.router)
    app.include_router(tasks.router)
    app.include_router(drafts.router)
    app.include_router(repos.router)
    app.include_router(chat.router)
    app.include_router(features.router)
    app.include_router(ws.router)

    @app.get("/api/healthz")
    async def healthz() -> dict:
        return {"status": "ok", "service": settings().service_name}

    @app.get("/api/readyz")
    async def readyz() -> dict:
        ready = settings().fake_k8s or state.cache.synced.is_set()
        return {
            "status": "ok" if ready else "starting",
            "natsConnected": state.nc is not None and state.nc.is_connected,
            "boardSynced": state.cache.synced.is_set(),
        }

    return app


app = create_app()
