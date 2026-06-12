import pytest
from sqlalchemy import select

import workspace.pipeline as pipeline_mod
from jarvis_core.db import Email, Task, create_engine_and_factory, init_models
from workspace.classify import (
    Category,
    Classification,
    DraftReply,
    ExtractedTask,
    effective_category,
)
from workspace.gmail import ParsedEmail
from workspace.pipeline import Pipeline


def test_low_confidence_fails_toward_task():
    c = Classification(category=Category.NEWSLETTER, confidence=0.4)
    assert effective_category(c) == Category.TASK
    c = Classification(category=Category.NEWSLETTER, confidence=0.9)
    assert effective_category(c) == Category.NEWSLETTER
    # Low-confidence task stays a task.
    c = Classification(category=Category.TASK, confidence=0.3)
    assert effective_category(c) == Category.TASK


class FakeGmail:
    def __init__(self):
        self.labeled: list[tuple[str, str]] = []
        self.drafts_created = 0

    def get_message(self, message_id: str) -> ParsedEmail:
        return ParsedEmail(
            gmail_message_id=message_id,
            thread_id="t1",
            subject="Please review the contract",
            from_addr="alice@example.com",
            to_addr="me@gmail.com",
            body_text="Can you review and reply by Friday?",
            message_id_header="<m@x>",
        )

    def apply_category(self, message_id: str, category: str, *, archive: bool) -> None:
        self.labeled.append((message_id, category))

    def create_reply_draft(self, email, reply_text, own_addr) -> str:
        self.drafts_created += 1
        return f"draft-{self.drafts_created}"


@pytest.fixture
async def session_factory(tmp_path):
    engine, factory = create_engine_and_factory(f"sqlite+aiosqlite:///{tmp_path}/ws.db")
    await init_models(engine)
    yield factory
    await engine.dispose()


@pytest.fixture
def live_mode(monkeypatch):
    from workspace import config

    monkeypatch.setenv("DRY_RUN", "false")
    config.settings.cache_clear()
    yield
    config.settings.cache_clear()


async def test_enqueue_is_idempotent(session_factory):
    pipeline = Pipeline(FakeGmail(), session_factory)
    await pipeline.enqueue(["m1", "m2"])
    await pipeline.enqueue(["m2", "m3"])
    async with session_factory() as session:
        rows = (await session.execute(select(Email))).scalars().all()
    assert sorted(r.gmail_message_id for r in rows) == ["m1", "m2", "m3"]


async def test_task_email_full_flow_and_replay_safety(session_factory, live_mode, monkeypatch):
    async def fake_classify(email):
        return Classification(
            category=Category.TASK,
            confidence=0.95,
            task=ExtractedTask(title="Review contract", description="Reply by Friday"),
        )

    async def fake_draft(email, task):
        return DraftReply(reply_text="Will do by Friday.", summary="Commits to review by Friday")

    monkeypatch.setattr(pipeline_mod.clf, "classify", fake_classify)
    monkeypatch.setattr(pipeline_mod.clf, "write_draft", fake_draft)

    gmail = FakeGmail()
    pipeline = Pipeline(gmail, session_factory, js=None, own_addr="me@gmail.com")
    await pipeline.enqueue(["m1"])
    await pipeline.process_pending()

    async with session_factory() as session:
        email_row = (await session.execute(select(Email))).scalar_one()
        task_row = (await session.execute(select(Task))).scalar_one()
    assert email_row.status == "done"
    assert email_row.category == "task"
    assert task_row.gmail_draft_id == "draft-1"
    assert gmail.labeled == [("m1", "task")]

    # Replay (redelivery/restart): no second label, task or draft.
    await pipeline.enqueue(["m1"])
    await pipeline.process_pending()
    async with session_factory() as session:
        assert len((await session.execute(select(Task))).scalars().all()) == 1
    assert gmail.drafts_created == 1
    assert len(gmail.labeled) == 1


async def test_newsletter_is_done_without_task(session_factory, live_mode, monkeypatch):
    async def fake_classify(email):
        return Classification(category=Category.NEWSLETTER, confidence=0.97)

    monkeypatch.setattr(pipeline_mod.clf, "classify", fake_classify)

    gmail = FakeGmail()
    pipeline = Pipeline(gmail, session_factory, own_addr="me@gmail.com")
    await pipeline.enqueue(["m9"])
    await pipeline.process_pending()

    async with session_factory() as session:
        email_row = (await session.execute(select(Email))).scalar_one()
        tasks = (await session.execute(select(Task))).scalars().all()
    assert email_row.status == "done"
    assert email_row.category == "newsletter"
    assert tasks == []


async def test_dry_run_never_mutates(session_factory, monkeypatch):
    async def fake_classify(email):
        return Classification(category=Category.TASK, confidence=0.9)

    monkeypatch.setattr(pipeline_mod.clf, "classify", fake_classify)

    gmail = FakeGmail()
    pipeline = Pipeline(gmail, session_factory, own_addr="me@gmail.com")
    await pipeline.enqueue(["m5"])
    await pipeline.process_pending()

    assert gmail.labeled == []
    assert gmail.drafts_created == 0
    async with session_factory() as session:
        email_row = (await session.execute(select(Email))).scalar_one()
    assert email_row.status == "pending"  # untouched, reprocessed when dry_run lifts
