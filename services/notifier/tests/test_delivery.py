import httpx
import pytest
from sqlalchemy import select

from jarvis_core.db import NotificationLog, create_engine_and_factory, init_models
from notifier.channels.base import DeliveryResult, Notification, NotificationChannel, Severity
from notifier.channels.discord import DiscordChannel
from notifier.consumer import Notifier
from notifier.router import Router, Rule


def note(event_id: str = "evt-1") -> Notification:
    return Notification(
        title="PR ready",
        body="body",
        url="https://github.com/x/pull/1",
        severity=Severity.ACTION,
        event_id=event_id,
        event_type="jarvis.workflow.pr.ready",
    )


async def test_discord_payload_and_429():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(429, headers={"Retry-After": "7"})
        return httpx.Response(204)

    channel = DiscordChannel(
        "discord",
        "https://discord.test/webhook",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    first = await channel.send(note())
    assert first.retryable and first.retry_after_seconds == 7

    second = await channel.send(note())
    assert second.ok
    import json

    payload = json.loads(requests[1].content)
    embed = payload["embeds"][0]
    assert embed["title"] == "PR ready"
    assert embed["color"] == 0xF59E0B


class RecordingChannel(NotificationChannel):
    def __init__(self, name: str = "discord"):
        self.name = name
        self.sent: list[Notification] = []

    async def send(self, notification: Notification) -> DeliveryResult:
        self.sent.append(notification)
        return DeliveryResult.success()


@pytest.fixture
async def session_factory(tmp_path):
    engine, factory = create_engine_and_factory(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    await init_models(engine)
    yield factory
    await engine.dispose()


def envelope(event_id: str = "evt-1") -> dict:
    return {
        "id": event_id,
        "type": "jarvis.workflow.pr.ready",
        "source": "operator",
        "time": "2026-06-12T10:00:00Z",
        "data": {
            "name": "gh-acme-api-42",
            "repository": "acme-api",
            "prUrl": "https://github.com/acme/api/pull/7",
            "prNumber": 7,
        },
    }


async def test_exactly_once_per_event(session_factory):
    channel = RecordingChannel()
    notifier = Notifier(
        Router([Rule(match="jarvis.workflow.pr.ready", channels=("discord",))]),
        {"discord": channel},
        session_factory,
        "http://dash",
    )

    assert await notifier.handle(envelope())
    assert await notifier.handle(envelope())  # redelivery → dedupe
    assert len(channel.sent) == 1
    assert channel.sent[0].url == "https://github.com/acme/api/pull/7"

    async with session_factory() as session:
        rows = (await session.execute(select(NotificationLog))).scalars().all()
        assert len(rows) == 1
        assert rows[0].status == "sent"


async def test_unrouted_events_ack_without_delivery(session_factory):
    channel = RecordingChannel()
    notifier = Notifier(Router([]), {"discord": channel}, session_factory, "http://dash")
    assert await notifier.handle(envelope())
    assert channel.sent == []
