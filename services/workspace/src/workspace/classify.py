"""LLM stages: classification (+ task extraction) and draft writing."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from jarvis_core.llm import build_model
from workspace.config import settings
from workspace.gmail import ParsedEmail

CONFIDENCE_FLOOR = 0.6


class Category(StrEnum):
    TASK = "task"
    INFORMATIONAL = "informational"
    NEWSLETTER = "newsletter"
    SPAM_ISH = "spam_ish"


class ExtractedTask(BaseModel):
    title: str = Field(description="Short imperative task title")
    description: str = Field(description="What needs to be done, with key details from the email")
    priority: str = Field(default="normal", description="low | normal | high")


class Classification(BaseModel):
    category: Category
    confidence: float = Field(ge=0, le=1)
    task: ExtractedTask | None = Field(
        default=None, description="Present only when category is task"
    )
    reasoning: str = ""


CLASSIFY_INSTRUCTIONS = """\
You triage a personal inbox. Classify each email:

- task: the sender expects ME to do something (reply with an answer, review,
  schedule, decide, pay, send something). Extract the task.
- informational: FYI content addressed to me, receipts, confirmations,
  notifications. No action expected.
- newsletter: bulk mailings, digests, marketing, product updates.
- spam_ish: unsolicited junk that somehow passed the spam filter.

When unsure between task and anything else, prefer task — a false task costs
seconds, a missed one costs trust.
"""


def effective_category(classification: Classification) -> Category:
    """Low confidence fails toward task/keep-in-inbox — never silently archive."""
    if classification.confidence < CONFIDENCE_FLOOR and classification.category != Category.TASK:
        return Category.TASK
    return classification.category


async def classify(email: ParsedEmail) -> Classification:
    agent = Agent(
        build_model(settings().classify_model),
        output_type=Classification,
        instructions=CLASSIFY_INSTRUCTIONS,
    )
    result = await agent.run(_render_email(email))
    return result.output


class DraftReply(BaseModel):
    reply_text: str = Field(description="The full plain-text reply body, ready to send")
    summary: str = Field(description="One sentence describing the reply, for the notification")


DRAFT_INSTRUCTIONS = """\
You draft email replies for the inbox owner. Write the reply they would send:
answer what was asked when the email contains the answer, otherwise commit to
the action with a realistic, non-specific timeline. Never invent facts,
amounts or dates. Style: {style}
"""


async def write_draft(email: ParsedEmail, task: ExtractedTask) -> DraftReply:
    agent = Agent(
        build_model(settings().draft_model),
        output_type=DraftReply,
        instructions=DRAFT_INSTRUCTIONS.format(style=settings().draft_style),
    )
    result = await agent.run(
        f"{_render_email(email)}\n\n## Extracted task\n{task.title}: {task.description}"
    )
    return result.output


def _render_email(email: ParsedEmail) -> str:
    return f"From: {email.from_addr}\nSubject: {email.subject}\n\n{email.body_text[:8000]}"
