"""analyzer stage — implemented in its build step (see plan)."""

from jarvis_core.envelope import AgentResultEnvelope, AgentStage, failure


def run() -> AgentResultEnvelope:
    return failure(
        AgentStage.ANALYZER,
        reason="NotImplemented",
        message="analyzer agent not implemented yet",
        retryable=False,
    )
