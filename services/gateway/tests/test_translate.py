from gateway.k8s.translate import to_board_item


def _cr(**status) -> dict:
    return {
        "metadata": {
            "name": "gh-acme-api-42",
            "creationTimestamp": "2026-06-12T08:00:00Z",
            "labels": {"jarvis.dev/repository": "acme-api"},
        },
        "spec": {
            "repositoryRef": {"name": "acme-api"},
            "source": {
                "type": "Issue",
                "issue": {
                    "provider": "github",
                    "id": "I_x",
                    "number": 42,
                    "url": "https://github.com/acme/api/issues/42",
                    "title": "Fix login loop",
                },
            },
        },
        "status": status,
    }


def test_fresh_cr_maps_to_pending():
    item = to_board_item(_cr())
    assert item.phase == "Pending"
    assert item.title == "Fix login loop"
    assert item.repository == "acme-api"
    assert item.failed is False


def test_status_fields_projected():
    item = to_board_item(
        _cr(
            phase="AwaitingMerge",
            analysis={"verdict": "CodeChange", "summary": "null deref in session handler"},
            development={"prUrl": "https://github.com/acme/api/pull/7", "prNumber": 7},
        )
    )
    assert item.phase == "AwaitingMerge"
    assert item.verdict == "CodeChange"
    assert item.pr_url.endswith("/pull/7")
    assert "null deref" in item.message


def test_failed_state():
    item = to_board_item(_cr(phase="Failed", failureReason="Boom: it broke"))
    assert item.failed is True
    assert item.message.startswith("Boom")


def test_feature_request_title():
    cr = _cr()
    cr["spec"]["source"] = {
        "type": "FeatureRequest",
        "featureRequest": {"description": "Add dark mode to the blog", "requestedBy": "chat"},
    }
    item = to_board_item(cr)
    assert item.title == "Add dark mode to the blog"
    assert item.source_type == "FeatureRequest"
