"""Analyzer stage: classify an issue as CodeChange | Misconfiguration |
NotActionable, grounded in a shallow clone of the repository."""

from __future__ import annotations

import asyncio
import tempfile
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from jarvis_agents.context import AgentContext, load_context, repo_token
from jarvis_agents.repotools import RepoReader
from jarvis_core import gitx, k8s
from jarvis_core.envelope import AgentResultEnvelope, AgentStage, success
from jarvis_core.llm import build_model


class Verdict(StrEnum):
    CODE_CHANGE = "CodeChange"
    MISCONFIGURATION = "Misconfiguration"
    NOT_ACTIONABLE = "NotActionable"


class AnalysisOutcome(BaseModel):
    verdict: Verdict
    summary: str = Field(description="One or two sentences a human reads on the board card")
    confidence: str = Field(description="high | medium | low")
    affected_areas: list[str] = Field(
        default_factory=list, description="Files or directories the work will touch"
    )
    reasoning: str = Field(description="Full reasoning for the report artifact")


INSTRUCTIONS = """\
You are the Jarvis analyzer. Classify the issue below for repository {repo}:

- CodeChange: the fix or feature requires changing code in this repository.
- Misconfiguration: the code is fine; the problem lives in deployment/runtime
  configuration (env vars, manifests, infrastructure) — the SRE agent will
  handle it against the GitOps repository.
- NotActionable: duplicate, question, spam, or not enough information to act.

Ground your verdict in the actual code: use the tools to read files, list
directories and grep before deciding. Be decisive; use confidence=low rather
than refusing to answer.
"""


def run() -> AgentResultEnvelope:
    ctx = load_context()
    return asyncio.run(_analyze(ctx))


async def _analyze(ctx: AgentContext) -> AgentResultEnvelope:
    issue = await _load_issue(ctx)

    workdir = Path(tempfile.mkdtemp(prefix="jarvis-")) / "repo"
    gitx.clone(ctx.clone_url, workdir, token=repo_token(), depth=1)
    reader = RepoReader(workdir)

    agent = Agent(
        build_model(ctx.model),
        output_type=AnalysisOutcome,
        instructions=INSTRUCTIONS.format(repo=ctx.repo_ref.full_name),
        tools=[reader.read_file, reader.list_dir, reader.grep],
    )

    prompt = (
        f"## Issue #{issue['number']}: {issue['title']}\n\n"
        f"{issue['body'] or '(no description)'}\n\n"
        f"Labels: {', '.join(issue['labels']) or '(none)'}\n\n"
        f"## Repository layout\n```\n{reader.tree_summary()}\n```"
    )
    result = await agent.run(prompt)
    outcome = result.output

    report_name = f"{ctx.workitem['metadata']['name']}-analysis"
    k8s.create_artifact_configmap(
        report_name,
        ctx.namespace,
        {"report.md": _report_markdown(issue, outcome)},
        owner=ctx.workitem,
    )

    return success(
        AgentStage.ANALYZER,
        {
            "verdict": outcome.verdict.value,
            "summary": outcome.summary[:500],
            "confidence": outcome.confidence,
        },
        artifacts={"report": report_name},
    )


async def _load_issue(ctx: AgentContext) -> dict:
    source = ctx.source
    if source["type"] == "FeatureRequest":
        fr = source["featureRequest"]
        return {
            "number": 0,
            "title": fr["description"][:120],
            "body": fr["description"],
            "labels": [],
        }
    forge = ctx.forge()
    try:
        issue = await forge.get_issue(ctx.repo_ref, source["issue"]["number"])
    finally:
        await forge.aclose()
    return {
        "number": issue.number,
        "title": issue.title,
        "body": issue.body,
        "labels": list(issue.labels),
    }


def _report_markdown(issue: dict, outcome: AnalysisOutcome) -> str:
    areas = "\n".join(f"- {a}" for a in outcome.affected_areas) or "- (none identified)"
    return (
        f"# Analysis: {issue['title']}\n\n"
        f"**Verdict:** {outcome.verdict.value} (confidence: {outcome.confidence})\n\n"
        f"**Summary:** {outcome.summary}\n\n"
        f"## Affected areas\n{areas}\n\n"
        f"## Reasoning\n{outcome.reasoning}\n"
    )
