"""Gmail history polling with transactional checkpointing.

The historyId checkpoint commits in the same transaction as the enqueued
email rows; a crash replays the page, which is safe because enqueue is
insert-or-ignore on gmail_message_id. A 404 (history expired, ~1 week)
triggers the full-inbox resync path.
"""

from __future__ import annotations

import asyncio
import logging
import random

from googleapiclient.errors import HttpError
from sqlalchemy.ext.asyncio import async_sessionmaker

from jarvis_core.db import GmailSyncState
from workspace.config import settings
from workspace.gmail import GmailClient
from workspace.pipeline import Pipeline

log = logging.getLogger(__name__)


class Poller:
    def __init__(self, gmail: GmailClient, pipeline: Pipeline, session_factory: async_sessionmaker):
        self.gmail = gmail
        self.pipeline = pipeline
        self.session_factory = session_factory

    async def bootstrap(self) -> str:
        """Load the checkpoint, or start 'from now' (no backfill)."""
        async with self.session_factory() as session:
            sync_state = await session.get(GmailSyncState, 1)
            if sync_state and sync_state.last_history_id:
                return sync_state.last_history_id

            profile = await asyncio.to_thread(self.gmail.get_profile)
            history_id = str(profile["historyId"])
            if sync_state is None:
                sync_state = GmailSyncState(
                    id=1,
                    email_address=profile.get("emailAddress", ""),
                    last_history_id=history_id,
                )
                session.add(sync_state)
            else:
                sync_state.last_history_id = history_id
            await session.commit()
            log.info("starting from now: historyId=%s (%s)", history_id, sync_state.email_address)
            return history_id

    async def run(self) -> None:
        cfg = settings()
        checkpoint = await self.bootstrap()
        while True:
            try:
                checkpoint = await self._cycle(checkpoint)
                await self.pipeline.process_pending()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("poll cycle failed")
            await asyncio.sleep(cfg.poll_interval_seconds + random.uniform(0, 5))

    async def _cycle(self, checkpoint: str) -> str:
        try:
            ids, latest = await asyncio.to_thread(self.gmail.history_since, checkpoint)
        except HttpError as exc:
            if exc.resp.status == 404:
                return await self._full_resync()
            raise

        if ids:
            log.info("history: %d new inbox message(s)", len(ids))
            await self.pipeline.enqueue(ids)
        if latest != checkpoint:
            await self._save_checkpoint(latest)
        return latest

    async def _full_resync(self) -> str:
        """History expired (long outage): resync from the inbox listing."""
        log.warning("historyId expired — full inbox resync")
        ids = await asyncio.to_thread(self.gmail.list_inbox_ids)
        await self.pipeline.enqueue(ids)
        profile = await asyncio.to_thread(self.gmail.get_profile)
        latest = str(profile["historyId"])
        await self._save_checkpoint(latest)
        return latest

    async def _save_checkpoint(self, history_id: str) -> None:
        async with self.session_factory() as session:
            sync_state = await session.get(GmailSyncState, 1)
            sync_state.last_history_id = history_id
            await session.commit()
