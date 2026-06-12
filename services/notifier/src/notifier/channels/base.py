from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum


class Severity(StrEnum):
    INFO = "info"
    ACTION = "action"  # human input wanted (merge a PR, review a draft)
    DANGER = "danger"


@dataclass(frozen=True)
class Notification:
    title: str
    body: str
    url: str
    severity: Severity
    fields: dict[str, str] = field(default_factory=dict)
    event_id: str = ""
    event_type: str = ""


@dataclass(frozen=True)
class DeliveryResult:
    ok: bool
    retryable: bool = False
    retry_after_seconds: float = 0
    reason: str = ""

    @classmethod
    def success(cls) -> DeliveryResult:
        return cls(ok=True)

    @classmethod
    def retry(cls, after: float, reason: str = "") -> DeliveryResult:
        return cls(ok=False, retryable=True, retry_after_seconds=after, reason=reason)

    @classmethod
    def permanent(cls, reason: str) -> DeliveryResult:
        return cls(ok=False, retryable=False, reason=reason)


class NotificationChannel(ABC):
    name: str

    @abstractmethod
    async def send(self, notification: Notification) -> DeliveryResult: ...
