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
from workspace.config import settings
from workspace.gmail import GmailClient
from workspace.pipeline import Pipeline
from workspace.poller import Poller

log = logging.getLogger(__name__)

state = {"gmail_ok": False, "last_history_id": ""}


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = settings()
    logging.basicConfig(level=cfg.log_level)

    engine, session_factory = create_engine_and_factory(cfg.database_url)
    await init_models(engine)

    background: list[asyncio.Task] = []
    nc = js = None
    if cfg.nats_url and not cfg.dry_run:
        try:
            nc, js = await asyncio.wait_for(bus.connect(cfg.nats_url), timeout=10)
        except Exception:  # noqa: BLE001
            log.exception("NATS unavailable; events disabled")

    creds_present = await asyncio.to_thread(Path(cfg.gmail_credentials_path).is_file)
    if not cfg.mail_enabled:
        log.info("mail feature disabled (MAIL_ENABLED=false); skipping Gmail entirely")
    elif creds_present:
        gmail = GmailClient(cfg.gmail_credentials_path)
        profile = await asyncio.to_thread(gmail.get_profile)
        own_addr = profile.get("emailAddress", "")
        log.info("gmail connected as %s (dry_run=%s)", own_addr, cfg.dry_run)
        state["gmail_ok"] = True

        if not cfg.dry_run:
            await asyncio.to_thread(gmail.ensure_labels)
        pipeline = Pipeline(gmail, session_factory, js=js, own_addr=own_addr)
        poller = Poller(gmail, pipeline, session_factory)
        background.append(asyncio.create_task(poller.run()))
    else:
        log.error(
            "gmail credentials missing at %s — poller disabled (run `make google-auth`)",
            cfg.gmail_credentials_path,
        )

    yield

    for task in background:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
    if nc is not None:
        with contextlib.suppress(Exception):
            await nc.drain()
    await engine.dispose()


app = FastAPI(title="jarvis-workspace", lifespan=lifespan)


@app.get("/api/healthz")
async def healthz() -> dict:
    return {"status": "ok", "service": settings().service_name}


@app.get("/api/readyz")
async def readyz() -> dict:
    return {"status": "ok" if state["gmail_ok"] else "degraded", "dryRun": settings().dry_run}


def run() -> None:
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run()
