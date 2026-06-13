"""Chat → feature request flow.

The model never free-texts a repository name: create_feature_request validates
against the live ManagedRepository list and unknown repos force a clarifying
turn instead. A successful tool call creates the WorkItem CR (the CRD is the
API) and the reply carries the workflow name for the tracking chip.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from pydantic_ai import Agent, RunContext

from gateway.config import settings
from gateway.k8s import ops
from jarvis_core.llm import build_model

log = logging.getLogger(__name__)

INSTRUCTIONS = """\
You are Jarvis, the assistant for a personal software-automation platform.
Users request features or fixes for their repositories in plain language.

- When the request and target repository are clear, call create_feature_request
  exactly once with a crisp, self-contained description (the developer agent
  receives only that text). Then tell the user it's queued.
- If the repository is ambiguous or the request too vague to implement,
  ask a short clarifying question instead.
- Keep replies to one or two sentences; no markdown headers.
"""


@dataclass
class ChatDeps:
    repos: list[str]
    session_id: str
    namespace: str
    created_workflow: str = ""
    created_repo: str = ""
    created_title: str = ""
    clarification: str = ""
    _ops: object = field(default=None)  # test seam


@dataclass
class ChatOutcome:
    reply: str
    workflow_name: str = ""


def build_chat_agent() -> Agent:
    agent = Agent(
        build_model(settings().chat_model),
        deps_type=ChatDeps,
        output_type=str,
        instructions=INSTRUCTIONS,
    )

    @agent.instructions
    def repo_list(ctx: RunContext[ChatDeps]) -> str:
        return "Configured repositories: " + (", ".join(ctx.deps.repos) or "(none yet)")

    @agent.tool
    async def create_feature_request(
        ctx: RunContext[ChatDeps], repository: str, title: str, description: str
    ) -> str:
        """Queue a feature request for an EXACT configured repository name."""
        deps = ctx.deps
        if repository not in deps.repos:
            return (
                f"ERROR: {repository!r} is not a configured repository. "
                f"Choose one of: {', '.join(deps.repos) or '(none configured)'}; "
                "if none fits, ask the user."
            )
        operations = deps._ops or ops
        name = await operations.create_feature_request_workitem(
            deps.namespace,
            repository=repository,
            description=f"{title}\n\n{description}",
            requested_by="dashboard",
            conversation_id=deps.session_id,
        )
        deps.created_workflow = name
        deps.created_repo = repository
        deps.created_title = title
        return f"created workflow {name}"

    return agent


async def name_session(history: list[dict], model=None) -> str:
    """Choose a short title for a conversation."""
    llm = model or build_model(settings().chat_model)
    agent = Agent(
        llm,
        output_type=str,
        instructions="You are a conversation summarizer. Distill the user's request from this brief exchange into a 3-5 word title. Omit 'Jarvis' and introductory pleasantries.",
    )
    prompt = _flatten_history(history)
    result = await agent.run(prompt)
    return result.output.strip().strip("'\"")


async def handle_message(history: list[dict], content: str, session_id: str) -> ChatOutcome:
    cfg = settings()
    repos = (
        []
        if cfg.fake_k8s
        else [r.name for r in await ops.list_repositories(cfg.workitem_namespace)]
    )
    deps = ChatDeps(repos=repos, session_id=session_id, namespace=cfg.workitem_namespace)

    agent = build_chat_agent()
    prompt = _flatten_history(history) + f"\nuser: {content}"
    result = await agent.run(prompt, deps=deps)
    return ChatOutcome(reply=result.output, workflow_name=deps.created_workflow)


def _flatten_history(history: list[dict], limit: int = 12) -> str:
    lines = [f"{m['role']}: {m['content']}" for m in history[-limit:]]
    return "\n".join(lines)
