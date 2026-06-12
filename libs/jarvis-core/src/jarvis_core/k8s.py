"""Kubernetes helpers for agents and watchers (sync client).

Agents are one-shot Jobs: they fetch their WorkItem + ManagedRepository, do
their work, and write artifact ConfigMaps owned by the WorkItem (so cleanup
is garbage collection). Only the operator writes WorkItem status.
"""

from __future__ import annotations

import base64

from kubernetes import client, config

GROUP = "jarvis.dev"
VERSION = "v1alpha1"


def load_config() -> None:
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()


def get_workitem(name: str, namespace: str) -> dict:
    return client.CustomObjectsApi().get_namespaced_custom_object(
        GROUP, VERSION, namespace, "workitems", name
    )


def get_managed_repository(name: str, namespace: str) -> dict:
    return client.CustomObjectsApi().get_namespaced_custom_object(
        GROUP, VERSION, namespace, "managedrepositories", name
    )


def list_managed_repositories(namespace: str) -> list[dict]:
    result = client.CustomObjectsApi().list_namespaced_custom_object(
        GROUP, VERSION, namespace, "managedrepositories"
    )
    return result.get("items", [])


def list_workitems(namespace: str, label_selector: str = "") -> list[dict]:
    result = client.CustomObjectsApi().list_namespaced_custom_object(
        GROUP, VERSION, namespace, "workitems", label_selector=label_selector
    )
    return result.get("items", [])


def create_workitem(namespace: str, body: dict) -> bool:
    """Create a WorkItem; False if it already exists (idempotent by name)."""
    try:
        client.CustomObjectsApi().create_namespaced_custom_object(
            GROUP, VERSION, namespace, "workitems", body
        )
        return True
    except client.ApiException as exc:
        if exc.status == 409:
            return False
        raise


def patch_workitem(name: str, namespace: str, patch: dict) -> None:
    client.CustomObjectsApi().patch_namespaced_custom_object(
        GROUP,
        VERSION,
        namespace,
        "workitems",
        name,
        patch,
        _content_type="application/merge-patch+json",
    )


def patch_managed_repository_status(name: str, namespace: str, status_patch: dict) -> None:
    client.CustomObjectsApi().patch_namespaced_custom_object_status(
        GROUP,
        VERSION,
        namespace,
        "managedrepositories",
        name,
        {"status": status_patch},
        _content_type="application/merge-patch+json",
    )


def create_artifact_configmap(name: str, namespace: str, data: dict[str, str], owner: dict) -> str:
    """Create/replace a ConfigMap owned by the WorkItem (GC'd together)."""
    body = client.V1ConfigMap(
        metadata=client.V1ObjectMeta(
            name=name,
            namespace=namespace,
            labels={"jarvis.dev/workitem": owner["metadata"]["name"]},
            owner_references=[
                client.V1OwnerReference(
                    api_version=f"{GROUP}/{VERSION}",
                    kind="WorkItem",
                    name=owner["metadata"]["name"],
                    uid=owner["metadata"]["uid"],
                )
            ],
        ),
        data=data,
    )
    api = client.CoreV1Api()
    try:
        api.create_namespaced_config_map(namespace, body)
    except client.ApiException as exc:
        if exc.status != 409:
            raise
        api.replace_namespaced_config_map(name, namespace, body)
    return name


def read_secret_token(name: str, namespace: str, key: str = "token") -> str:
    secret = client.CoreV1Api().read_namespaced_secret(name, namespace)
    raw = secret.data.get(key, "")
    return base64.b64decode(raw).decode().strip()
