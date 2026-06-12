"""Write-side K8s operations the gateway performs (async client):
card actions, ManagedRepository CRUD, chat-created WorkItems."""

from __future__ import annotations

import hashlib

from kubernetes_asyncio import client

from jarvis_core.dto import RepositoryInfo

GROUP, VERSION = "jarvis.dev", "v1alpha1"
ANNOTATION_ACTION = "jarvis.dev/requested-action"


async def request_action(namespace: str, name: str, action: str) -> None:
    async with client.ApiClient() as api_client:
        api = client.CustomObjectsApi(api_client)
        await api.patch_namespaced_custom_object(
            GROUP,
            VERSION,
            namespace,
            "workitems",
            name,
            {"metadata": {"annotations": {ANNOTATION_ACTION: action}}},
        )


async def list_repositories(namespace: str) -> list[RepositoryInfo]:
    async with client.ApiClient() as api_client:
        api = client.CustomObjectsApi(api_client)
        result = await api.list_namespaced_custom_object(
            GROUP, VERSION, namespace, "managedrepositories"
        )
    return [_to_repo_info(item) for item in result.get("items", [])]


async def create_repository(
    namespace: str,
    *,
    name: str,
    provider: str,
    owner: str,
    repo: str,
    require_labels: list[str],
    credentials_secret_name: str,
) -> RepositoryInfo:
    body = {
        "apiVersion": f"{GROUP}/{VERSION}",
        "kind": "ManagedRepository",
        "metadata": {"name": name},
        "spec": {
            "provider": provider,
            "owner": owner,
            "name": repo,
            "credentialsSecretRef": {"name": credentials_secret_name},
            "issueSelector": {"requireLabels": require_labels} if require_labels else None,
        },
    }
    body["spec"] = {k: v for k, v in body["spec"].items() if v is not None}
    async with client.ApiClient() as api_client:
        api = client.CustomObjectsApi(api_client)
        created = await api.create_namespaced_custom_object(
            GROUP, VERSION, namespace, "managedrepositories", body
        )
    return _to_repo_info(created)


async def delete_repository(namespace: str, name: str) -> None:
    async with client.ApiClient() as api_client:
        api = client.CustomObjectsApi(api_client)
        await api.delete_namespaced_custom_object(
            GROUP, VERSION, namespace, "managedrepositories", name
        )


async def create_feature_request_workitem(
    namespace: str,
    *,
    repository: str,
    description: str,
    requested_by: str,
    conversation_id: str,
) -> str:
    digest = hashlib.sha1(f"{conversation_id}:{description}".encode()).hexdigest()[:8]
    name = f"fr-{digest}"
    body = {
        "apiVersion": f"{GROUP}/{VERSION}",
        "kind": "WorkItem",
        "metadata": {
            "name": name,
            "labels": {
                "jarvis.dev/repository": repository,
                "jarvis.dev/source-type": "FeatureRequest",
            },
        },
        "spec": {
            "repositoryRef": {"name": repository},
            "source": {
                "type": "FeatureRequest",
                "featureRequest": {
                    "description": description,
                    "requestedBy": requested_by,
                    "conversationId": conversation_id,
                },
            },
        },
    }
    async with client.ApiClient() as api_client:
        api = client.CustomObjectsApi(api_client)
        try:
            await api.create_namespaced_custom_object(GROUP, VERSION, namespace, "workitems", body)
        except client.ApiException as exc:
            if exc.status != 409:  # already tracked → fine, return the name
                raise
    return name


def _to_repo_info(cr: dict) -> RepositoryInfo:
    spec = cr.get("spec", {})
    status = cr.get("status", {})
    return RepositoryInfo(
        name=cr["metadata"]["name"],
        provider=spec.get("provider", ""),
        owner=spec.get("owner", ""),
        repo=spec.get("name", ""),
        suspended=bool(spec.get("suspend", False)),
        require_labels=(spec.get("issueSelector") or {}).get("requireLabels", []) or [],
        gitops_repo_url=(spec.get("gitops") or {}).get("repoUrl", ""),
        active_work_items=status.get("activeWorkItems", 0),
    )
