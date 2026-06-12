from __future__ import annotations

import logging

from notifier.channels.base import DeliveryResult, Notification, NotificationChannel

log = logging.getLogger("notifier.channel.log")


class LogChannel(NotificationChannel):
    """Stdout channel for debugging and dry-runs."""

    def __init__(self, name: str = "log"):
        self.name = name

    async def send(self, notification: Notification) -> DeliveryResult:
        log.info(
            "[%s] %s — %s (%s)",
            notification.severity,
            notification.title,
            notification.body,
            notification.url,
        )
        return DeliveryResult.success()
