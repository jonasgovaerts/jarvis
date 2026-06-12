"""Process-wide singletons assembled in the lifespan and used by routers."""

from __future__ import annotations

from dataclasses import dataclass, field

from nats.aio.client import Client
from nats.js import JetStreamContext
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from gateway.events.fanout import WebSocketHub
from gateway.k8s.watcher import BoardCache


@dataclass
class AppState:
    cache: BoardCache = field(default_factory=BoardCache)
    hub: WebSocketHub = field(default_factory=WebSocketHub)
    nc: Client | None = None
    js: JetStreamContext | None = None
    engine: AsyncEngine | None = None
    session_factory: async_sessionmaker | None = None


state = AppState()
