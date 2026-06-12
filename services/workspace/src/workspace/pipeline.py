"""Per-email pipeline: fetch → classify → label → task → draft → events.

Every step records completion in emails.status so a restart resumes
half-processed emails without repeating Gmail mutations:
  pending → classified (labels applied, task row created) → done (draft created)
DRY_RUN logs decisions and stops before any mutation or event.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from jarvis_core import bus
from jarvis_core.db import Email, Task
from jarvis_core.events import EmailDraftReady, EmailTaskCreated
from workspace import classify as clf
from workspace.config import settings
from workspace.gmail import GmailClient, ParsedEmail

log = logging.getLogger(__name__)


class Pipeline:
    def __init__(
        self, gmail: GmailClient, session_factory: async_sessionmaker, js=None, own_addr: str = ""
    ):
        self.gmail = gmail
        self.session_factory = session_factory
        self.js = js
        self.own_addr = own_addr

    async def enqueue(self, message_ids: list[str]) -> None:
        """Insert-or-ignore email rows; the worker picks up status=pending."""
        async with self.session_factory() as session:
            for message_id in message_ids:
                exists = await session.scalar(
                    select(Email.id).where(Email.gmail_message_id == message_id)
                )
                if exists is None:
                    session.add(Email(gmail_message_id=message_id, status="pending"))
            await session.commit()

    async def process_pending(self) -> int:
        async with self.session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(Email).where(Email.status.in_(["pending", "classified"])).limit(20)
                    )
                )
                .scalars()
                .all()
            )
        for email_row in rows:
            try:
                await self._process_one(email_row.id)
            except Exception:
                log.exception("pipeline failed for email %s", email_row.gmail_message_id)
                async with self.session_factory() as session:
                    row = await session.get(Email, email_row.id)
                    row.status = "failed"
                    await session.commit()
        return len(rows)

    async def _process_one(self, email_pk: str) -> None:
        cfg = settings()
        async with self.session_factory() as session:
            row = await session.get(Email, email_pk)
            message_id = row.gmail_message_id
            status = row.status

        parsed = await asyncio.to_thread(self.gmail.get_message, message_id)

        if status == "pending":
            classification = await clf.classify(parsed)
            category = clf.effective_category(classification)
            log.info(
                "classified %s (%s): %s → %s (%.2f)%s",
                message_id,
                parsed.subject[:60],
                classification.category,
                category,
                classification.confidence,
                " [DRY_RUN]" if cfg.dry_run else "",
            )
            if cfg.dry_run:
                return

            await asyncio.to_thread(
                self.gmail.apply_category,
                message_id,
                category.value,
                archive=cfg.archive_non_tasks,
            )

            task_id = ""
            async with self.session_factory() as session:
                row = await session.get(Email, email_pk)
                row.subject = parsed.subject[:500]
                row.from_addr = parsed.from_addr[:320]
                row.thread_id = parsed.thread_id
                row.category = category.value
                row.confidence = f"{classification.confidence:.2f}"

                if category == clf.Category.TASK:
                    extracted = classification.task or clf.ExtractedTask(
                        title=parsed.subject[:200] or "Reply to email",
                        description=f"Email from {parsed.from_addr}",
                    )
                    task = Task(
                        email_id=row.id,
                        title=extracted.title[:300],
                        description=extracted.description,
                        priority=extracted.priority,
                        gmail_message_id=message_id,
                    )
                    session.add(task)
                    await session.flush()
                    task_id = task.id
                    row.status = "classified"
                else:
                    row.status = "done"
                    row.processed_at = datetime.now(UTC)
                await session.commit()

            if task_id:
                await self._publish(
                    "jarvis.email.task.created",
                    EmailTaskCreated(
                        task_id=task_id,
                        gmail_message_id=message_id,
                        thread_id=parsed.thread_id,
                        subject=parsed.subject[:300],
                        from_addr=parsed.from_addr,
                        title=(
                            classification.task.title if classification.task else parsed.subject
                        )[:300],
                        priority=classification.task.priority if classification.task else "normal",
                    ),
                    msg_id=f"email-task:{message_id}",
                )
            else:
                return  # non-task: finished

        # status == classified (or just became it): draft still owed.
        await self._draft_for(email_pk, parsed)

    async def _draft_for(self, email_pk: str, parsed: ParsedEmail) -> None:
        async with self.session_factory() as session:
            task = await session.scalar(select(Task).where(Task.email_id == email_pk))
            if task is None:
                return
            if task.gmail_draft_id:  # crash-replay guard: draft already exists
                return
            extracted = clf.ExtractedTask(
                title=task.title, description=task.description, priority=task.priority
            )

        draft = await clf.write_draft(parsed, extracted)
        draft_id = await asyncio.to_thread(
            self.gmail.create_reply_draft, parsed, draft.reply_text, self.own_addr
        )

        async with self.session_factory() as session:
            task_row = await session.get(Task, task.id)
            task_row.gmail_draft_id = draft_id
            email_row = await session.get(Email, email_pk)
            email_row.status = "done"
            email_row.processed_at = datetime.now(UTC)
            await session.commit()

        await self._publish(
            "jarvis.email.draft.ready",
            EmailDraftReady(
                task_id=task.id,
                gmail_message_id=parsed.gmail_message_id,
                gmail_draft_id=draft_id,
                thread_id=parsed.thread_id,
                subject=parsed.subject[:300],
                summary=draft.summary[:500],
            ),
            msg_id=f"email-draft:{parsed.gmail_message_id}",
        )

    async def _publish(self, subject: str, payload, *, msg_id: str) -> None:
        if self.js is None:
            log.info("NATS disabled; skipping %s", subject)
            return
        await bus.publish(self.js, subject, payload, source="workspace", msg_id=msg_id)
