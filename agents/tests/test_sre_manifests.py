from pathlib import Path

import pytest
import yaml

from jarvis_agents.sre import _set_helm_values_tag, _set_kustomize_tag
from jarvis_core.envelope import AgentFailure


def test_kustomize_tag_pinned(tmp_path: Path):
    f = tmp_path / "kustomization.yaml"
    f.write_text(
        yaml.safe_dump(
            {
                "resources": ["../../base"],
                "images": [{"name": "ghcr.io/acme/api", "newTag": "sha-old1234"}],
            }
        )
    )
    _set_kustomize_tag(f, "sha-new5678")
    doc = yaml.safe_load(f.read_text())
    assert doc["images"][0]["newTag"] == "sha-new5678"
    assert doc["resources"] == ["../../base"]


def test_kustomize_without_images_fails_cleanly(tmp_path: Path):
    f = tmp_path / "kustomization.yaml"
    f.write_text(yaml.safe_dump({"resources": ["../../base"]}))
    with pytest.raises(AgentFailure, match="images"):
        _set_kustomize_tag(f, "sha-x")


def test_helm_values_tag_pinned(tmp_path: Path):
    f = tmp_path / "values.yaml"
    f.write_text(yaml.safe_dump({"image": {"repository": "ghcr.io/acme/api", "tag": "old"}}))
    _set_helm_values_tag(f, "sha-new5678")
    doc = yaml.safe_load(f.read_text())
    assert doc["image"]["tag"] == "sha-new5678"


def test_helm_values_without_tag_fails_cleanly(tmp_path: Path):
    f = tmp_path / "values.yaml"
    f.write_text(yaml.safe_dump({"replicaCount": 1}))
    with pytest.raises(AgentFailure, match="image.tag"):
        _set_helm_values_tag(f, "sha-x")
