"""Durable JetStream consumer → router → channels, with per-channel dedupe."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging

from nats.js import JetStreamContext
from nats.js.api import AckPolicy, ConsumerConfig
from sqlalchemy.ext.asyncio import async_sessionmaker

from jarvis_core.events import STREAM_NAME
from notifier import dedupe
from notifier.channels.base import NotificationChannel
from notifier.router import Router
from notifier.templates import render

log = logging.getLogger(__name__)


class Notifier:
    def __init__(
        self,
        router: Router,
        channels: dict[str, NotificationChannel],
        session_factory: async_sessionmaker,
        dashboard_url: str,
    ):
        self.router = router
        self.channels = channels
        self.session_factory = session_factory
        self.dashboard_url = dashboard_url

    async def handle(self, envelope: dict) -> bool:
        """Process one event; False asks for redelivery (nak)."""
        subject = envelope.get("type", "")
        targets = self.router.route(subject)
        if not targets:
            return True

        notification = render(envelope, self.dashboard_url)
        if notification is None:
            return True

        all_ok = True
        for channel_name in targets:
            channel = self.channels.get(channel_name)
            if channel is None:
                log.warning("rule routes %s to unknown channel %s", subject, channel_name)
                continue
            async with self.session_factory() as session:
                if not await dedupe.claim(session, notification.event_id, channel.name):
                    continue  # already delivered
                result = await channel.send(notification)
                if result.ok:
                    await dedupe.mark(session, notification.event_id, channel.name, "sent")
                elif result.retryable:
                    log.warning("retryable delivery failure on %s: %s", channel.name, result.reason)
                    all_ok = False  # leave log row 'pending'; nak triggers redelivery
                else:
                    log.error("permanent delivery failure on %s: %s", channel.name, result.reason)
                    await dedupe.mark(session, notification.event_id, channel.name, "failed")
        return all_ok


async def run_consumer(js: JetStreamContext, notifier: Notifier) -> None:
    consumer = await js.pull_subscribe(
        "jarvis.>",
        durable="notifier",
        stream=STREAM_NAME,
        config=ConsumerConfig(ack_policy=AckPolicy.EXPLICIT, max_deliver=5, ack_wait=30),
    )
    log.info("notifier consumer running")
    while True:
        try:
            msgs = await consumer.fetch(batch=10, timeout=10)
        except TimeoutError:
            continue
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("fetch failed; retrying")
            await asyncio.sleep(5)
            continue

        for msg in msgs:
            try:
                envelope = json.loads(msg.data)
            except json.JSONDecodeError:
                await msg.term()  # malformed forever — drop it
                continue
            try:
                if await notifier.handle(envelope):
                    await msg.ack()
                else:
                    await msg.nak(delay=15)
            except Exception:  # noqa: BLE001
                log.exception("handling failed for %s", envelope.get("type"))
                with contextlib.suppress(Exception):
                    await msg.nak(delay=30)
