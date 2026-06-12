"""Developer stage: implement the change on a branch and open a PR.

Pure Pydantic AI tool loop (read/grep/list + write/edit + guarded
run_command), capped by a request budget. On CI fix loops the existing branch
is reused and the failure analysis is injected into the prompt.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from jarvis_agents import verify
from jarvis_agents.context import AgentContext, load_context, repo_token
from jarvis_agents.devtools import RepoEditor
from jarvis_core import gitx
from jarvis_core.envelope import AgentFailure, AgentResultEnvelope, AgentStage, success
from jarvis_core.llm import build_model

log = logging.getLogger(__name__)

MAX_REQUESTS = 60
MAX_FIX_ROUNDS = 3
FIX_ROUND_REQUESTS = 25


class DevelopmentSummary(BaseModel):
    changes_description: str = Field(description="What was changed and why, for the PR body")
    commit_message: str = Field(description="Conventional one-line commit subject")
    pr_title: str
    tests_run: str = Field(
        default="", description="Which tests/linters were executed and their outcome"
    )


INSTRUCTIONS = """\
You are the Jarvis developer agent working on repository {repo}.
Implement the requested change with the provided tools:

- Explore first: list_dir, read_file, grep. Match the existing code style.
- Edit with edit_file (exact unique string replace) or write_file.
- Verify your work: run the project's tests/linters with run_command where
  the tooling exists in this environment; fix what you break. After you
  finish, the harness runs the repository's lint and test commands itself —
  failures come back to you and the change cannot ship until they pass, so
  running them yourself first is faster.
- Keep the change minimal and focused on the request. Do not refactor
  unrelated code. Do not touch CI config unless that is the task.
- When you are done, return the structured summary. The diff must not be empty.
"""


def run() -> AgentResultEnvelope:
    ctx = load_context()
    return asyncio.run(_develop(ctx))


async def _develop(ctx: AgentContext) -> AgentResultEnvelope:
    token = repo_token()
    issue = _describe_task(ctx)
    branch = _branch_name(ctx)
    status = ctx.workitem.get("status", {})
    previous = status.get("development")
    ci_feedback = (status.get("ci") or {}).get("failureAnalysis", "")

    workdir = Path(tempfile.mkdtemp(prefix="jarvis-")) / "repo"
    gitx.clone(ctx.clone_url, workdir, token=token)
    gitx.configure_identity(workdir)

    if previous and previous.get("branch"):
        branch = previous["branch"]
        # Continue the existing PR branch on fix loops.
        gitx.run_git(["fetch", "origin", branch], cwd=workdir, token=token)
        gitx.run_git(["checkout", branch], cwd=workdir)
        replace_remote = False
        log.info("continuing fix-loop on existing branch %s", branch)
    else:
        gitx.run_git(["checkout", "-b", branch], cwd=workdir)
        # A prior attempt may have pushed this branch and then died before
        # its envelope recorded the result. Nothing references that history
        # (no recorded development result, branch is jarvis-owned), so this
        # fresh attempt replaces it instead of bouncing off non-fast-forward.
        leftover = gitx.run_git(
            ["ls-remote", "--heads", "origin", branch], cwd=workdir, token=token
        )
        replace_remote = leftover.strip() != ""
        if replace_remote:
            log.info("orphaned remote branch %s found — will replace it", branch)

    editor = RepoEditor(workdir)
    agent = Agent(
        build_model(ctx.model),
        output_type=DevelopmentSummary,
        instructions=INSTRUCTIONS.format(repo=ctx.repo_ref.full_name),
        tools=[
            editor.read_file,
            editor.list_dir,
            editor.grep,
            editor.write_file,
            editor.edit_file,
            editor.run_command,
        ],
    )

    prompt = issue
    if ci_feedback:
        prompt += (
            "\n\n## CI failed on the previous attempt — fix this first\n"
            f"{ci_feedback}\n"
            "The branch already contains the previous attempt's changes."
        )
    prompt += f"\n\n## Repository layout\n```\n{editor.tree_summary()}\n```"

    log.info("starting implementation loop (request budget %d)", MAX_REQUESTS)
    result = await agent.run(prompt, usage_limits=UsageLimits(request_limit=MAX_REQUESTS))
    log.info("model loop finished after %d requests", result.usage().requests)
    summary = result.output

    if not gitx.run_git(["status", "--porcelain"], cwd=workdir).strip():
        raise AgentFailure(
            reason="NoChangesProduced",
            message="agent finished without modifying any files",
            retryable=True,
        )

    # Hard gate: the repo's own lint/tests must pass before anything is
    # pushed. Failures go back into the model loop, bounded by MAX_FIX_ROUNDS.
    for fix_round in range(MAX_FIX_ROUNDS + 1):
        failures = await asyncio.to_thread(verify.run_checks, workdir)
        if not failures:
            break
        if fix_round == MAX_FIX_ROUNDS:
            raise AgentFailure(
                reason="VerificationFailed",
                message="; ".join(f.command for f in failures)[:400],
                retryable=True,
            )
        log.info(
            "verification round %d: %d check(s) failing — sending back to the model",
            fix_round + 1,
            len(failures),
        )
        result = await agent.run(
            verify.format_feedback(failures),
            message_history=result.all_messages(),
            usage_limits=UsageLimits(request_limit=FIX_ROUND_REQUESTS),
        )
        summary = result.output

    gitx.run_git(["add", "-A"], cwd=workdir)
    gitx.run_git(["commit", "-m", summary.commit_message], cwd=workdir)
    push_args = ["push", "-u", "origin", branch]
    if replace_remote:
        push_args.insert(1, "--force")
    gitx.run_git(push_args, cwd=workdir, token=token)
    head_sha = gitx.run_git(["rev-parse", "HEAD"], cwd=workdir).strip()

    forge = ctx.forge()
    try:
        pr = await forge.find_pull_request(ctx.repo_ref, head=branch)
        if pr is None:
            base = await forge.get_default_branch(ctx.repo_ref)
            log.info("opening pull request for %s", branch)
            pr = await forge.create_pull_request(
                ctx.repo_ref,
                head=branch,
                base=base,
                title=summary.pr_title,
                body=_pr_body(ctx, summary),
            )
    finally:
        await forge.aclose()

    return success(
        AgentStage.DEVELOPER,
        {
            "branch": branch,
            "prUrl": pr.url,
            "prNumber": pr.number,
            "headSha": head_sha,
        },
    )


def _describe_task(ctx: AgentContext) -> str:
    source = ctx.source
    analysis = ctx.workitem.get("status", {}).get("analysis") or {}
    parts = []
    if source["type"] == "Issue":
        issue = source["issue"]
        parts.append(f"## Task: issue #{issue['number']} — {issue['title']}\n{issue['url']}")
    else:
        fr = source["featureRequest"]
        parts.append(
            f"## Task: feature request from {fr.get('requestedBy', 'chat')}\n{fr['description']}"
        )
    if analysis.get("summary"):
        parts.append(f"## Analyzer summary\n{analysis['summary']}")
    return "\n\n".join(parts)


def _branch_name(ctx: AgentContext) -> str:
    source = ctx.source
    if source["type"] == "Issue":
        return f"jarvis/issue-{source['issue']['number']}"
    digest = hashlib.sha1(source["featureRequest"]["description"].encode()).hexdigest()[:8]
    return f"jarvis/fr-{digest}"


def _pr_body(ctx: AgentContext, summary: DevelopmentSummary) -> str:
    source = ctx.source
    link = ""
    if source["type"] == "Issue":
        link = f"Closes {source['issue']['url']}\n\n"
    tests = f"\n\n## Verification\n{summary.tests_run}" if summary.tests_run else ""
    return (
        f"{link}{summary.changes_description}{tests}\n\n"
        f"---\n🤖 Opened by Jarvis (WorkItem `{ctx.workitem['metadata']['name']}`)"
    )
