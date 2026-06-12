from notifier.router import DEFAULT_ROUTING, Router, subject_matches


def test_subject_matching_semantics():
    assert subject_matches("jarvis.workflow.pr.ready", "jarvis.workflow.pr.ready")
    assert subject_matches("jarvis.workflow.*.ready", "jarvis.workflow.pr.ready")
    assert subject_matches("jarvis.>", "jarvis.workflow.pr.ready")
    assert subject_matches("jarvis.workflow.>", "jarvis.workflow.failed")
    assert not subject_matches("jarvis.workflow.pr.ready", "jarvis.workflow.pr.opened")
    assert not subject_matches("jarvis.workflow", "jarvis.workflow.failed")
    assert not subject_matches("jarvis.workflow.*", "jarvis.workflow.pr.ready")
    assert not subject_matches("jarvis.>", "jarvis")


def test_first_match_wins():
    router = Router.from_yaml(
        """
rules:
  - match: "jarvis.workflow.pr.ready"
    channels: [discord]
  - match: "jarvis.workflow.>"
    channels: []
default_channels: [log]
"""
    )
    assert router.route("jarvis.workflow.pr.ready") == ("discord",)
    assert router.route("jarvis.workflow.phase.changed") == ()
    assert router.route("jarvis.email.draft.ready") == ("log",)


def test_default_routing_notifies_the_right_events():
    router = Router.from_yaml(DEFAULT_ROUTING)
    assert router.route("jarvis.workflow.pr.ready") == ("discord",)
    assert router.route("jarvis.workflow.failed") == ("discord",)
    assert router.route("jarvis.email.draft.ready") == ("discord",)
    assert router.route("jarvis.workflow.phase.changed") == ()
    assert router.route("jarvis.chat.request.created") == ()
