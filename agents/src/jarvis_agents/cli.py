"""Entrypoint for agent Jobs: ``jarvis-agent <stage>``.

The operator passes context via env vars (JARVIS_WORKITEM_NAME/NAMESPACE,
JARVIS_STAGE, JARVIS_MODEL); the agent fetches the WorkItem and its
ManagedRepository from the Kubernetes API, does its work, and reports back by
writing an AgentResultEnvelope to /dev/termination-log — never by touching the
CR status.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import traceback

from jarvis_core.envelope import AgentFailure, AgentStage, failure, write_termination_message


def main() -> int:
    # Jobs are observed via `kubectl logs`; everything goes to stdout.
    logging.basicConfig(
        level=os.getenv("JARVIS_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
    log = logging.getLogger("jarvis_agents")

    parser = argparse.ArgumentParser(prog="jarvis-agent")
    parser.add_argument("stage", choices=[s.value for s in AgentStage])
    args = parser.parse_args()
    stage = AgentStage(args.stage)
    log.info(
        "stage=%s workitem=%s/%s model=%s",
        stage.value,
        os.getenv("JARVIS_WORKITEM_NAMESPACE", "?"),
        os.getenv("JARVIS_WORKITEM_NAME", "?"),
        os.getenv("JARVIS_MODEL", "?"),
    )

    try:
        runner = _resolve(stage)
        envelope = runner()
    except AgentFailure as exc:
        traceback.print_exc()
        envelope = failure(stage, reason=exc.reason, message=exc.message, retryable=exc.retryable)
    except Exception as exc:  # noqa: BLE001 - the envelope is the error channel
        traceback.print_exc()
        envelope = failure(stage, reason=type(exc).__name__, message=str(exc), retryable=False)

    if envelope.outcome == "success":
        log.info("done: %s", envelope.result)
    else:
        log.error("failed: %s — %s", envelope.error.reason, envelope.error.message)
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
