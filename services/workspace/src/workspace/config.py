from functools import lru_cache

from jarvis_core.settings import JarvisSettings


class WorkspaceSettings(JarvisSettings):
    service_name: str = "workspace"

    database_url: str = "sqlite+aiosqlite:///./jarvis-workspace.db"

    # authorized_user.json from the OAuth bootstrap (mounted Secret in-cluster).
    gmail_credentials_path: str = "/var/run/secrets/jarvis/gmail/authorized_user.json"

    poll_interval_seconds: int = 45

    # One-time catch-up: enqueue the most recent inbox messages at startup.
    # Idempotent (already-processed mail is skipped), so leaving it on only
    # costs one messages.list per pod start.
    backfill_on_start: bool = False
    backfill_max_messages: int = 200

    # Log every decision but never mutate Gmail or publish events.
    dry_run: bool = True

    # Archive (remove INBOX) for non-task categories. Task emails always stay.
    archive_non_tasks: bool = True

    classify_model: str = "claude-haiku"
    draft_model: str = "claude-sonnet"

    # Style hints injected into the draft-writing prompt.
    draft_style: str = "Concise, friendly, professional. Sign off as Jonas."


@lru_cache
def settings() -> WorkspaceSettings:
    return WorkspaceSettings()
