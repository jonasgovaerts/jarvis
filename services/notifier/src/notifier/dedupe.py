"""Consume-side idempotency: at most one delivery per (event_id, channel).

INSERT ... ON CONFLICT DO NOTHING claims the delivery; a crash between send
and ack means one rare duplicate — for a Discord ping that beats a missed
"PR ready".
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from jarvis_core.db import NotificationLog


async def claim(session: AsyncSession, event_id: str, channel: str) -> bool:
    """True if this worker claimed the delivery (or retries a failed one)."""
    dialect = session.bind.dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = (
            pg_insert(NotificationLog)
            .values(event_id=event_id, channel=channel, status="pending")
            .on_conflict_do_nothing()
        )
    else:
        stmt = (
            sqlite_insert(NotificationLog)
            .values(event_id=event_id, channel=channel, status="pending")
            .on_conflict_do_nothing()
        )
    result = await session.execute(stmt)
    await session.commit()
    if result.rowcount:
        return True

    row = await session.scalar(
        select(NotificationLog).where(
            NotificationLog.event_id == event_id, NotificationLog.channel == channel
        )
    )
    # Re-claim only deliveries that previously failed permanently? No — those
    # were terminal. Re-claim 'pending' rows (crashed mid-send) by allowing the
    # send; 'sent' rows are done.
    return row is not None and row.status == "pending"


async def mark(session: AsyncSession, event_id: str, channel: str, status: str) -> None:
    row = await session.get(NotificationLog, (event_id, channel))
    if row is not None:
        row.status = status
        await session.commit()
