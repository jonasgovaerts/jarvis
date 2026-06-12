import pytest

from jarvis_agents.sre import wait_for_merge_build
from jarvis_core.envelope import AgentFailure
from jarvis_core.forge import CheckRun, RepoRef

REPO = RepoRef(owner="acme", name="api")


def run(name: str, status: str, conclusion: str = "") -> CheckRun:
    return CheckRun(name=name, status=status, conclusion=conclusion)


class ScriptedForge:
    """Returns one check-run snapshot per poll."""

    def __init__(self, snapshots: list[list[CheckRun]]):
        self.snapshots = snapshots
        self.calls = 0

    async def list_check_runs(self, repo, sha):
        snapshot = self.snapshots[min(self.calls, len(self.snapshots) - 1)]
        self.calls += 1
        return snapshot


@pytest.fixture(autouse=True)
def fast_polls(monkeypatch):
    monkeypatch.setenv("JARVIS_BUILD_POLL_SECONDS", "0")
    monkeypatch.setenv("JARVIS_BUILD_MAX_POLLS", "5")
    monkeypatch.setenv("JARVIS_BUILD_GRACE_POLLS", "2")


async def test_waits_until_build_green():
    forge = ScriptedForge(
        [
            [run("build", "in_progress")],
            [run("build", "in_progress")],
            [run("build", "completed", "success")],
        ]
    )
    await wait_for_merge_build(forge, REPO, "abc1234def")
    assert forge.calls == 3


async def test_failed_build_aborts_rollout_permanently():
    forge = ScriptedForge([[run("build", "completed", "failure")]])
    with pytest.raises(AgentFailure) as err:
        await wait_for_merge_build(forge, REPO, "abc1234def")
    assert err.value.reason == "MergeBuildFailed"
    assert err.value.retryable is False


async def test_repo_without_ci_proceeds_after_grace():
    forge = ScriptedForge([[]])
    await wait_for_merge_build(forge, REPO, "abc1234def")
    assert forge.calls == 3  # grace_polls + 1


async def test_still_running_at_budget_is_retryable():
    forge = ScriptedForge([[run("build", "in_progress")]])
    with pytest.raises(AgentFailure) as err:
        await wait_for_merge_build(forge, REPO, "abc1234def")
    assert err.value.reason == "MergeBuildTimeout"
    assert err.value.retryable is True
