"""devops stage — implemented in its build step (see plan)."""

from jarvis_core.envelope import AgentResultEnvelope, AgentStage, failure


def run() -> AgentResultEnvelope:
    return failure(
        AgentStage.DEVOPS,
        reason="NotImplemented",
        message="devops agent not implemented yet",
        retryable=False,
    )
