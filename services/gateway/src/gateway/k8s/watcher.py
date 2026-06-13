"""WorkItem watch loop feeding the in-memory board cache.

GET /api/workflows is served from this cache — never from a live K8s call.
Fixture mode (FAKE_K8S=1) seeds the cache from canned items so the frontend
can be developed and demoed without a cluster.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from kubernetes_asyncio import client, config, watch

from gateway.k8s.translate import to_board_item
from jarvis_core.dto import BoardItem
from jarvis_core.events import SourceType, WorkItemPhase

log = logging.getLogger(__name__)

GROUP, VERSION, PLURAL = "jarvis.dev", "v1alpha1", "workitems"


class BoardCache:
    def __init__(self) -> None:
        self._items: dict[str, BoardItem] = {}
        self._raw: dict[str, dict] = {}
        self.synced = asyncio.Event()

    def upsert(self, cr: dict) -> None:
        item = to_board_item(cr)
        self._items[item.name] = item
        self._raw[item.name] = cr

    def delete(self, name: str) -> None:
        self._items.pop(name, None)
        self._raw.pop(name, None)

    def replace_all(self, crs: list[dict]) -> None:
        self._items.clear()
        self._raw.clear()
        for cr in crs:
            self.upsert(cr)

    def list(self, phase: str | None = None, repo: str | None = None) -> list[BoardItem]:
        items = list(self._items.values())
        if phase:
            items = [i for i in items if i.phase == phase]
        if repo:
            items = [i for i in items if i.repository == repo]
        return sorted(items, key=lambda i: i.created_at, reverse=True)

    def get_raw(self, name: str) -> dict | None:
        return self._raw.get(name)


async def run_watcher(cache: BoardCache, namespace: str) -> None:
    """List+watch with relist on 410; resourceVersion handled by the lib."""
    try:
        config.load_incluster_config()
    except config.ConfigException:
        await config.load_kube_config()

    async with client.ApiClient() as api_client:
        api = client.CustomObjectsApi(api_client)
        while True:
            try:
                initial = await api.list_namespaced_custom_object(GROUP, VERSION, namespace, PLURAL)
                cache.replace_all(initial.get("items", []))
                cache.synced.set()
                version = initial["metadata"]["resourceVersion"]

                w = watch.Watch()
                # kubernetes_asyncio's Watch is the async iterator itself (no
                # aclose); close it explicitly so the response is released.
                try:
                    async for event in w.stream(
                        api.list_namespaced_custom_object,
                        GROUP,
                        VERSION,
                        namespace,
                        PLURAL,
                        resource_version=version,
                        timeout_seconds=300,
                    ):
                        obj = event["object"]
                        if event["type"] == "DELETED":
                            cache.delete(obj["metadata"]["name"])
                        else:
                            cache.upsert(obj)
                finally:
                    await w.close()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("workitem watch failed; relisting in 5s")
                await asyncio.sleep(5)


def seed_fixtures(cache: BoardCache) -> None:
    """Demo/dev data covering every column."""
    now = datetime.now(UTC)

    def item(name: str, phase: WorkItemPhase, **kw) -> BoardItem:
        defaults = dict(
            name=name,
            repository="jarvis-playground",
            title=kw.pop("title", name),
            source_type=kw.pop("source_type", SourceType.ISSUE),
            phase=phase,
            created_at=now - timedelta(hours=kw.pop("age_h", 2)),
        )
        return BoardItem(**defaults | kw)

    fixtures = [
        item("gh-acme-api-41", WorkItemPhase.PENDING, title="Rate-limit login attempts"),
        item("gh-acme-api-42", WorkItemPhase.ANALYZING, title="Fix login redirect loop"),
        item(
            "gh-acme-api-39",
            WorkItemPhase.DEVELOPING,
            title="Add CSV export to reports",
            verdict="CodeChange",
            message="Code change in reports module",
            age_h=5,
        ),
        item(
            "gh-acme-api-37",
            WorkItemPhase.AWAITING_CI,
            title="Bump httpx and fix timeouts",
            verdict="CodeChange",
            pr_url="https://github.com/acme/api/pull/91",
            age_h=8,
        ),
        item(
            "fr-7a1b2c3d",
            WorkItemPhase.AWAITING_MERGE,
            title="Add dark mode to the blog",
            source_type=SourceType.FEATURE_REQUEST,
            pr_url="https://github.com/acme/blog/pull/12",
            age_h=20,
        ),
        item(
            "gh-acme-api-35",
            WorkItemPhase.ROLLOUT_CHECK,
            title="Fix memory leak in worker",
            verdict="CodeChange",
            pr_url="https://github.com/acme/api/pull/88",
            age_h=26,
        ),
        item(
            "gh-acme-api-30",
            WorkItemPhase.SUCCEEDED,
            title="Upgrade Postgres driver",
            age_h=30,
        ),
        item(
            "gh-acme-api-33",
            WorkItemPhase.FAILED,
            failed=True,
            title="Migrate auth to OIDC",
            message="CI failed after 2 fix attempts: integration tests time out",
            age_h=12,
        ),
    ]
    for board_item in fixtures:
        cache._items[board_item.name] = board_item  # noqa: SLF001 - fixture seeding
    cache.synced.set()
