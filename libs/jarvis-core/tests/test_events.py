import pytest

from jarvis_core.events import (
    SUBJECTS,
    WorkflowPhaseChanged,
    WorkflowPRReady,
    WorkItemPhase,
    make_envelope,
    parse_payload,
)


def test_all_subjects_follow_naming_scheme():
    for subject in SUBJECTS:
        parts = subject.split(".")
        assert parts[0] == "jarvis"
        assert 3 <= len(parts) <= 4, f"{subject} must be jarvis.<domain>.<entity>[.<verb>]"


def test_envelope_roundtrip_camelcase():
    payload = WorkflowPhaseChanged(
        name="gh-acme-api-42",
        repository="acme/api",
        from_phase=WorkItemPhase.ANALYZING,
        to_phase=WorkItemPhase.DEVELOPING,
    )
    env = make_envelope("jarvis.workflow.phase.changed", payload, source="operator")
    assert env.type == "jarvis.workflow.phase.changed"
    assert env.data["fromPhase"] == "Analyzing"  # camelCase on the wire

    parsed = parse_payload(env)
    assert isinstance(parsed, WorkflowPhaseChanged)
    assert parsed.to_phase is WorkItemPhase.DEVELOPING


def test_envelope_rejects_wrong_payload_type():
    payload = WorkflowPRReady(name="x", repository="r", pr_url="u", pr_number=1)
    with pytest.raises(TypeError):
        make_envelope("jarvis.workflow.phase.changed", payload, source="operator")


def test_envelope_rejects_unknown_subject():
    payload = WorkflowPRReady(name="x", repository="r", pr_url="u", pr_number=1)
    with pytest.raises(ValueError):
        make_envelope("jarvis.workflow.nope", payload, source="operator")
