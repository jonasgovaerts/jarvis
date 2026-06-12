"""Entrypoint for agent Jobs: ``jarvis-agent <stage>``.

The operator passes context via env vars (JARVIS_WORKITEM_NAME/NAMESPACE,
JARVIS_STAGE, JARVIS_MODEL); the agent fetches the WorkItem and its
ManagedRepository from the Kubernetes API, does its work, and reports back by
writing an AgentResultEnvelope to /dev/termination-log — never by touching the
CR status.
"""

from __future__ import annotations

import argparse
import sys
import traceback

from jarvis_core.envelope import AgentStage, failure, write_termination_message


def main() -> int:
    parser = argparse.ArgumentParser(prog="jarvis-agent")
    parser.add_argument("stage", choices=[s.value for s in AgentStage])
    args = parser.parse_args()
    stage = AgentStage(args.stage)

    try:
        runner = _resolve(stage)
        envelope = runner()
    except Exception as exc:  # noqa: BLE001 - the envelope is the error channel
        traceback.print_exc()
        envelope = failure(stage, reason=type(exc).__name__, message=str(exc), retryable=False)

    try:
        write_termination_message(envelope)
    except OSError:
        # Not in a pod (local run): fall back to stdout so the result is visible.
        print(envelope.to_wire())
    return 0 if envelope.outcome == "success" else 1


def _resolve(stage: AgentStage):
    match stage:
        case AgentStage.ANALYZER:
            from jarvis_agents.analyzer import run
        case AgentStage.DEVELOPER:
            from jarvis_agents.developer import run
        case AgentStage.DEVOPS:
            from jarvis_agents.devops import run
        case AgentStage.SRE:
            from jarvis_agents.sre import run
    return run


if __name__ == "__main__":
    sys.exit(main())
