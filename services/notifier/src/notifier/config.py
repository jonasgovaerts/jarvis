from functools import lru_cache

from jarvis_core.settings import JarvisSettings


class NotifierSettings(JarvisSettings):
    service_name: str = "notifier"

    database_url: str = "sqlite+aiosqlite:///./jarvis-notifier.db"

    # Where notification links point.
    dashboard_url: str = "http://localhost:5173"

    discord_webhook_url: str = ""

    # Optional path to a routing rules YAML (ConfigMap mount); built-in
    # defaults apply when empty.
    routing_config_path: str = ""


@lru_cache
def settings() -> NotifierSettings:
    return NotifierSettings()
