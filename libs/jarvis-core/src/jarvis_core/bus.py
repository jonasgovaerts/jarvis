"""NATS JetStream helpers shared by the Python services.

Mirrors the operator's publisher semantics: CloudEvents-lite envelopes,
deterministic Nats-Msg-Id headers, one JARVIS_EVENTS stream over jarvis.>.
"""

from __future__ import annotations

import nats
from nats.aio.client import Client
from nats.js import JetStreamContext
from nats.js.api import RetentionPolicy, StorageType, StreamConfig

from jarvis_core.events import (
    STREAM_NAME,
    STREAM_SUBJECTS,
    EventEnvelope,
    _EventModel,
    make_envelope,
)

THIRTY_DAYS = 30 * 24 * 3600


async def connect(url: str, *, connect_timeout: int = 5) -> tuple[Client, JetStreamContext]:
    """Fail fast when the server is unreachable at startup (callers degrade
    gracefully); reconnect forever once a connection has been established."""
    nc = await nats.connect(
        url,
        connect_timeout=connect_timeout,
        max_reconnect_attempts=-1,
    )
    js = nc.jetstream()
    await ensure_stream(js)
    return nc, js


async def ensure_stream(js: JetStreamContext) -> None:
    config = StreamConfig(
        name=STREAM_NAME,
        subjects=[STREAM_SUBJECTS],
        storage=StorageType.FILE,
        retention=RetentionPolicy.LIMITS,
        max_age=THIRTY_DAYS,
        duplicate_window=600,
    )
    import contextlib

    try:
        await js.add_stream(config)
    except Exception:  # noqa: BLE001 - already exists (or concurrent create)
        # Racing another service is fine — the stream exists either way.
        with contextlib.suppress(Exception):
            await js.update_stream(config)


async def publish(
    js: JetStreamContext,
    subject: str,
    payload: _EventModel,
    *,
    source: str,
    msg_id: str,
) -> EventEnvelope:
    envelope = make_envelope(subject, payload, source=source)
    await js.publish(
        subject,
        envelope.model_dump_json(by_alias=True).encode(),
        headers={"Nats-Msg-Id": msg_id},
    )
    return envelope
