from __future__ import annotations

import httpx

from notifier.channels.base import DeliveryResult, Notification, NotificationChannel, Severity

COLORS = {
    Severity.INFO: 0x22D3EE,  # arc-reactor cyan
    Severity.ACTION: 0xF59E0B,  # amber
    Severity.DANGER: 0xF43F5E,  # red
}


class DiscordChannel(NotificationChannel):
    def __init__(self, name: str, webhook_url: str, client: httpx.AsyncClient | None = None):
        self.name = name
        self._webhook_url = webhook_url
        self._client = client or httpx.AsyncClient(timeout=15)

    async def send(self, notification: Notification) -> DeliveryResult:
        embed: dict = {
            "title": notification.title,
            "description": notification.body[:4000],
            "color": COLORS[notification.severity],
        }
        if notification.url:
            embed["url"] = notification.url
        if notification.fields:
            embed["fields"] = [
                {"name": key, "value": value[:1024], "inline": True}
                for key, value in notification.fields.items()
            ][:10]

        try:
            response = await self._client.post(self._webhook_url, json={"embeds": [embed]})
        except httpx.HTTPError as exc:
            return DeliveryResult.retry(after=30, reason=str(exc))

        if response.status_code in (200, 204):
            return DeliveryResult.success()
        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", "5"))
            return DeliveryResult.retry(after=retry_after, reason="rate limited")
        if 500 <= response.status_code < 600:
            return DeliveryResult.retry(after=30, reason=f"HTTP {response.status_code}")
        return DeliveryResult.permanent(f"HTTP {response.status_code}: {response.text[:200]}")
