import json

import pytest

from jarvis_core.envelope import (
    MAX_BYTES,
    AgentStage,
    failure,
    parse_termination_message,
    success,
    write_termination_message,
)


def test_success_roundtrip(tmp_path):
    env = success(
        AgentStage.ANALYZER,
        {"verdict": "CodeChange", "summary": "null deref in handler"},
        artifacts={"report": "gh-acme-api-42-analysis"},
    )
    target = tmp_path / "termination-log"
    write_termination_message(env, path=target)

    parsed = parse_termination_message(target.read_text())
    assert parsed.outcome == "success"
    assert parsed.stage == AgentStage.ANALYZER
    assert parsed.result["verdict"] == "CodeChange"
    assert parsed.artifacts == {"report": "gh-acme-api-42-analysis"}
    assert parsed.error is None


def test_failure_envelope():
    env = failure(AgentStage.DEVELOPER, "CloneFailed", "auth denied", retryable=True)
    parsed = parse_termination_message(env.to_wire())
    assert parsed.outcome == "failure"
    assert parsed.error.reason == "CloneFailed"
    assert parsed.error.retryable is True
    assert parsed.result is None


def test_oversized_free_text_is_truncated():
    env = failure(AgentStage.DEVOPS, "CIFailed", "x" * 10_000, retryable=False)
    wire = env.to_wire()
    assert len(wire.encode()) <= MAX_BYTES
    assert "[truncated]" in json.loads(wire)["error"]["message"]


def test_oversized_structured_result_raises():
    env = success(AgentStage.SRE, {f"key{i}": "v" * 100 for i in range(100)})
    with pytest.raises(ValueError, match="artifact ConfigMap"):
        env.to_wire()
