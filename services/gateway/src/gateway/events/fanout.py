"""NATS → WebSocket fan-out and the workflow_events history projection.

The live WS feed uses a plain core-NATS subscription (fire-and-forget; the
frontend refetches on reconnect). History uses a durable JetStream consumer
so the phase timeline misses nothing across gateway restarts.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from datetime import datetime

from fastapi import WebSocket
from nats.aio.client import Client
from nats.js import JetStreamContext
from nats.js.api import AckPolicy, ConsumerConfig
from sqlalchemy.ext.asyncio import async_sessionmaker

from jarvis_core.db import WorkflowEvent
from jarvis_core.events import STREAM_NAME

log = logging.getLogger(__name__)


class WebSocketHub:
    """Tracks connected dashboard clients and broadcasts event envelopes."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def add(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.add(ws)

    async def remove(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, message: dict) -> None:
        async with self._lock:
            clients = list(self._clients)
        for ws in clients:
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001 - dead client; reaped on next ping
                await self.remove(ws)


async def run_ws_fanout(nc: Client, hub: WebSocketHub) -> None:
    """Forward every jarvis.> envelope to connected dashboards as-is."""
    sub = await nc.subscribe("jarvis.>")
    try:
        async for msg in sub.messages:
            try:
                envelope = json.loads(msg.data)
            except json.JSONDecodeError:
                continue
            await hub.broadcast({"type": "event", "event": envelope})
    except asyncio.CancelledError:
        with contextlib.suppress(Exception):
            await sub.unsubscribe()
        raise


async def run_history_consumer(js: JetStreamContext, session_factory: async_sessionmaker) -> None:
    """Durable consumer appending every event to workflow_events."""
    consumer = await js.pull_subscribe(
        "jarvis.>",
        durable="gateway-history",
        stream=STREAM_NAME,
        config=ConsumerConfig(ack_policy=AckPolicy.EXPLICIT, max_deliver=5, ack_wait=30),
    )
    while True:
        try:
            msgs = await consumer.fetch(batch=20, timeout=10)
        except TimeoutError:
            continue
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("history fetch failed; retrying")
            await asyncio.sleep(5)
            continue
        for msg in msgs:
            try:
                envelope = json.loads(msg.data)
                data = envelope.get("data", {})
                name = data.get("name") or data.get("workflowName") or ""
                if name:
                    async with session_factory() as session:
                        session.add(
                            WorkflowEvent(
                                workflow_name=name,
                                subject=envelope.get("type", msg.subject),
                                time=_parse_time(envelope.get("time")),
                                data=data,
                            )
                        )
                        await session.commit()
                await msg.ack()
            except Exception:  # noqa: BLE001
                log.exception("history append failed; nak for redelivery")
                with contextlib.suppress(Exception):
                    await msg.nak(delay=10)


def _parse_time(raw: str | None) -> datetime:
    if not raw:
        return datetime.now()
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now()
