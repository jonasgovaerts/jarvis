from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import uvicorn
from fastapi import FastAPI

from issue_watcher.config import settings
from issue_watcher.sync import sync_repository
from jarvis_core import k8s

log = logging.getLogger(__name__)

state = {"last_cycle": None, "healthy": True}


async def poll_loop() -> None:
    cfg = settings()
    ns = cfg.workitem_namespace
    while True:
        try:
            repos = await asyncio.to_thread(k8s.list_managed_repositories, ns)
            now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            for mr in repos:
                if mr["spec"].get("suspend"):
                    continue
                try:
                    await sync_repository(mr, ns, now_iso)
                except Exception:
                    log.exception("sync failed for %s", mr["metadata"]["name"])
            state["last_cycle"] = now_iso
            state["healthy"] = True
        except Exception:
            log.exception("poll cycle failed")
            state["healthy"] = False
        await asyncio.sleep(cfg.poll_interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=settings().log_level)
    k8s.load_config()
    task = asyncio.create_task(poll_loop())
    yield
    task.cancel()


app = FastAPI(title="jarvis-issue-watcher", lifespan=lifespan)


@app.get("/api/healthz")
async def healthz() -> dict:
    return {"status": "ok", "service": settings().service_name}


@app.get("/api/readyz")
async def readyz() -> dict:
    return {"status": "ok" if state["healthy"] else "degraded", "lastCycle": state["last_cycle"]}


def run() -> None:
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run()
