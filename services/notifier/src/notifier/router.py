"""Routing rules: NATS-wildcard subject match → channel names, first match wins."""

from __future__ import annotations

from dataclasses import dataclass

import yaml


def subject_matches(pattern: str, subject: str) -> bool:
    """NATS semantics: '*' matches exactly one token, '>' the full remainder."""
    pat = pattern.split(".")
    sub = subject.split(".")
    for i, token in enumerate(pat):
        if token == ">":
            return i < len(sub)
        if i >= len(sub):
            return False
        if token not in ("*", sub[i]):
            return False
    return len(pat) == len(sub)


@dataclass(frozen=True)
class Rule:
    match: str
    channels: tuple[str, ...]


class Router:
    def __init__(self, rules: list[Rule], default_channels: tuple[str, ...] = ()):
        self.rules = rules
        self.default_channels = default_channels

    def route(self, subject: str) -> tuple[str, ...]:
        for rule in self.rules:
            if subject_matches(rule.match, subject):
                return rule.channels
        return self.default_channels

    @classmethod
    def from_yaml(cls, text: str) -> Router:
        doc = yaml.safe_load(text) or {}
        rules = [
            Rule(match=raw["match"], channels=tuple(raw.get("channels", [])))
            for raw in doc.get("rules", [])
        ]
        return cls(rules, tuple(doc.get("default_channels", [])))


DEFAULT_ROUTING = """\
rules:
  - match: "jarvis.workflow.pr.ready"
    channels: [discord]
  - match: "jarvis.workflow.failed"
    channels: [discord]
  - match: "jarvis.workflow.rollout.completed"
    channels: [discord]
  - match: "jarvis.email.draft.ready"
    channels: [discord]
  # board-only events — explicit empty rules document the decision
  - match: "jarvis.workflow.>"
    channels: []
  - match: "jarvis.>"
    channels: []
default_channels: []
"""
