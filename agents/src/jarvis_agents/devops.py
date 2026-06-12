"""DevOps stage: follow CI for the PR's head SHA; on failure, produce an
LLM root-cause summary the operator feeds back into the developer loop.

The LLM is only invoked on failure — green runs cost zero tokens.
"""

from __future__ import annotations

import asyncio
import os

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from jarvis_agents.context import AgentContext, load_context
from jarvis_core.envelope import AgentFailure, AgentResultEnvelope, AgentStage, success
from jarvis_core.llm import build_model

POLL_INTERVAL = int(os.getenv("JARVIS_CI_POLL_SECONDS", "30"))
# The Job's activeDeadlineSeconds is the hard stop; this is the soft budget.
MAX_POLLS = int(os.getenv("JARVIS_CI_MAX_POLLS", "100"))


class FailureDiagnosis(BaseModel):
    root_cause: str = Field(description="Concise root cause of the CI failure")
    suggested_action: str = Field(description="fix | abort")


def run() -> AgentResultEnvelope:
    ctx = load_context()
    return asyncio.run(_watch_ci(ctx))


async def _watch_ci(ctx: AgentContext) -> AgentResultEnvelope:
    development = ctx.workitem.get("status", {}).get("development") or {}
    head_sha = development.get("headSha", "")
    pr_number = development.get("prNumber", 0)
    if not head_sha or not pr_number:
        raise AgentFailure(
            reason="MissingDevelopmentResult",
            message="status.development.headSha/prNumber not set",
            retryable=False,
        )

    auto_merge = bool(ctx.repo["spec"].get("pipeline", {}).get("autoMerge", False))
    forge = ctx.forge()
    try:
        for _ in range(MAX_POLLS):
            checks = await forge.list_check_runs(ctx.repo_ref, head_sha)
            if not checks:
                # No CI configured on the repo: trivially green.
                await asyncio.sleep(POLL_INTERVAL)
                checks = await forge.list_check_runs(ctx.repo_ref, head_sha)
                if not checks:
                    return await _passed(ctx, forge, pr_number, auto_merge, url="")

            failed = [c for c in checks if c.finished_bad]
            if failed:
                diagnosis = await _diagnose(ctx, failed)
                return success(
                    AgentStage.DEVOPS,
                    {
                        "status": "Failed",
                        "checkSuiteUrl": failed[0].url,
                        "failureAnalysis": diagnosis,
                    },
                )

            if all(c.finished_ok for c in checks):
                return await _passed(ctx, forge, pr_number, auto_merge, url=checks[0].url)

            await asyncio.sleep(POLL_INTERVAL)
    finally:
        await forge.aclose()

    return success(
        AgentStage.DEVOPS,
        {"status": "TimedOut", "failureAnalysis": "CI did not finish within the polling budget"},
    )


async def _passed(
    ctx: AgentContext, forge, pr_number: int, auto_merge: bool, url: str
) -> AgentResultEnvelope:
    result: dict = {"status": "Passed", "checkSuiteUrl": url, "merged": False}
    if auto_merge:
        merge_sha = await forge.merge_pull_request(ctx.repo_ref, pr_number)
        result.update(merged=True, mergeSha=merge_sha)
    return success(AgentStage.DEVOPS, result)


async def _diagnose(ctx: AgentContext, failed: list) -> str:
    names = ", ".join(c.name for c in failed)
    agent = Agent(
        build_model(ctx.model),
        output_type=FailureDiagnosis,
        instructions=(
            "You analyze CI failures for an automated fix loop. Be specific and"
            " actionable: name the failing check and the most likely cause."
        ),
    )
    try:
        result = await agent.run(
            f"CI checks failed for PR head: {names}. Check URLs: "
            + "; ".join(c.url for c in failed if c.url)
            + ". Summarize the likely root cause for the developer agent."
        )
        return f"Failing checks: {names}. {result.output.root_cause}"
    except Exception:  # noqa: BLE001 - diagnosis is best-effort
        return f"Failing checks: {names}."
