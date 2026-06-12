from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from jarvis_core import bus
from jarvis_core.db import create_engine_and_factory, init_models
from notifier.channels.base import NotificationChannel
from notifier.channels.discord import DiscordChannel
from notifier.channels.logchan import LogChannel
from notifier.config import settings
from notifier.consumer import Notifier, run_consumer
from notifier.router import DEFAULT_ROUTING, Router

log = logging.getLogger(__name__)

state = {"connected": False}


def build_channels() -> dict[str, NotificationChannel]:
    cfg = settings()
    channels: dict[str, NotificationChannel] = {"log": LogChannel()}
    if cfg.discord_webhook_url:
        channels["discord"] = DiscordChannel("discord", cfg.discord_webhook_url)
    else:
        log.warning("DISCORD_WEBHOOK_URL not set — 'discord' routes fall back to log")
        channels["discord"] = LogChannel("discord")
    return channels


def build_router() -> Router:
    cfg = settings()
    if cfg.routing_config_path and Path(cfg.routing_config_path).is_file():
        return Router.from_yaml(Path(cfg.routing_config_path).read_text())
    return Router.from_yaml(DEFAULT_ROUTING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = settings()
    logging.basicConfig(level=cfg.log_level)

    engine, session_factory = create_engine_and_factory(cfg.database_url)
    await init_models(engine)

    nc, js = await bus.connect(cfg.nats_url)
    state["connected"] = True

    notifier = Notifier(build_router(), build_channels(), session_factory, cfg.dashboard_url)
    task = asyncio.create_task(run_consumer(js, notifier))

    yield

    task.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await task
    with contextlib.suppress(Exception):
        await nc.drain()
    await engine.dispose()


app = FastAPI(title="jarvis-notifier", lifespan=lifespan)


@app.get("/api/healthz")
async def healthz() -> dict:
    return {"status": "ok", "service": settings().service_name}


@app.get("/api/readyz")
async def readyz() -> dict:
    return {"status": "ok" if state["connected"] else "starting"}


def run() -> None:
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run()
