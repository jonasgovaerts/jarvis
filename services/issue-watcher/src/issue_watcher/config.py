from functools import lru_cache

from jarvis_core.settings import JarvisSettings


class WatcherSettings(JarvisSettings):
    service_name: str = "issue-watcher"

    # Namespace holding ManagedRepository + WorkItem CRs.
    workitem_namespace: str = "jarvis"
    poll_interval_seconds: int = 60


@lru_cache
def settings() -> WatcherSettings:
    return WatcherSettings()
