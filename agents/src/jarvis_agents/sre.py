"""SRE stage: decide whether the merged change needs a rollout and, if so,
bump the GitOps repository (kustomize image pin or Helm values).

Misconfiguration-verdict items skip development entirely; here the agent
inspects the GitOps manifests and proposes the configuration fix itself.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_ai import Agent

from jarvis_agents.context import AgentContext, gitops_token, load_context
from jarvis_agents.devtools import RepoEditor
from jarvis_core import gitx
from jarvis_core.envelope import AgentFailure, AgentResultEnvelope, AgentStage, success
from jarvis_core.llm import build_model


class RolloutDecision(BaseModel):
    decision: str = Field(description="Required | NotRequired")
    reason: str


def run() -> AgentResultEnvelope:
    ctx = load_context()
    return asyncio.run(_check_rollout(ctx))


async def _check_rollout(ctx: AgentContext) -> AgentResultEnvelope:
    gitops = ctx.repo["spec"].get("gitops")
    if not gitops:
        return success(
            AgentStage.SRE,
            {"decision": "NotRequired", "reason": "repository has no gitops mapping"},
        )

    status = ctx.workitem.get("status", {})
    analysis = status.get("analysis") or {}
    if analysis.get("verdict") == "Misconfiguration":
        return await _fix_configuration(ctx, gitops)

    ci = status.get("ci") or {}
    merge_sha = ci.get("mergeSha", "")
    if not merge_sha:
        raise AgentFailure(
            reason="MissingMergeSha",
            message="status.ci.mergeSha not set — cannot pin an image tag",
            retryable=False,
        )

    decision = await _decide(ctx)
    if decision.decision != "Required":
        return success(AgentStage.SRE, {"decision": "NotRequired", "reason": decision.reason})

    return await _bump_image(ctx, gitops, merge_sha, decision.reason)


async def _decide(ctx: AgentContext) -> RolloutDecision:
    """Application code merged → almost always a rollout; ask the model only
    to catch the exceptions (docs-only changes, CI-only changes)."""
    status = ctx.workitem.get("status", {})
    summary = (status.get("analysis") or {}).get("summary", "")
    title = ctx.workitem["spec"]["source"].get("issue", {}).get("title", "") or summary
    agent = Agent(
        build_model(ctx.model),
        output_type=RolloutDecision,
        instructions=(
            "Decide if this merged change needs a deployment rollout. Code or"
            " dependency changes → Required. Documentation-only, CI-only, or"
            " test-only changes → NotRequired. When unsure, choose Required."
        ),
    )
    result = await agent.run(f"Change: {title}\nAnalyzer summary: {summary}")
    return result.output


async def _bump_image(
    ctx: AgentContext, gitops: dict, merge_sha: str, reason: str
) -> AgentResultEnvelope:
    """Pin the new image tag in the gitops repo. Convention: the target app's
    CI tags images sha-<7char-commit>."""
    token = gitops_token()
    workdir = Path(tempfile.mkdtemp(prefix="jarvis-gitops-")) / "repo"
    branch = gitops.get("targetBranch", "main")
    gitx.clone(gitops["repoUrl"], workdir, token=token, branch=branch)
    gitx.configure_identity(workdir)

    target = workdir / gitops["path"]
    if not target.is_dir():
        raise AgentFailure(
            reason="GitOpsPathMissing",
            message=f"path {gitops['path']!r} not found in gitops repo",
            retryable=False,
        )

    tag = f"sha-{merge_sha[:7]}"
    style = gitops.get("manifestStyle", "KustomizeImage")
    if style == "KustomizeImage":
        _set_kustomize_tag(target / "kustomization.yaml", tag)
    else:
        _set_helm_values_tag(target / "values.yaml", tag)

    wi_name = ctx.workitem["metadata"]["name"]
    gitx.run_git(["add", "-A"], cwd=workdir)
    if not gitx.run_git(["status", "--porcelain"], cwd=workdir).strip():
        return success(
            AgentStage.SRE,
            {
                "decision": "NotRequired",
                "reason": f"image already at {tag}",
                "argocdApp": gitops.get("argocdApp", ""),
            },
        )
    gitx.run_git(
        ["commit", "-m", f"chore(deploy): {ctx.repo_ref.name} → {tag} (jarvis {wi_name})"],
        cwd=workdir,
    )

    result: dict = {
        "decision": "Required",
        "reason": reason,
        "argocdApp": gitops.get("argocdApp", ""),
    }
    if gitops.get("updateStrategy", "PullRequest") == "DirectPush":
        gitx.run_git(["push", "origin", branch], cwd=workdir, token=token)
        result["gitopsCommitSha"] = gitx.run_git(["rev-parse", "HEAD"], cwd=workdir).strip()
    else:
        pr_branch = f"jarvis/rollout-{wi_name}"
        gitx.run_git(["checkout", "-b", pr_branch], cwd=workdir)
        gitx.run_git(["push", "-u", "origin", pr_branch], cwd=workdir, token=token)
        pr = await _open_gitops_pr(ctx, gitops, pr_branch, tag)
        result["gitopsPrUrl"] = pr
    return success(AgentStage.SRE, result)


async def _open_gitops_pr(ctx: AgentContext, gitops: dict, head: str, tag: str) -> str:
    owner_repo = gitops["repoUrl"].rstrip("/").removesuffix(".git").split("/")[-2:]
    from jarvis_core.forge import GitHubForge, RepoRef

    forge = GitHubForge(gitops_token())
    try:
        pr = await forge.create_pull_request(
            RepoRef(owner=owner_repo[0], name=owner_repo[1]),
            head=head,
            base=gitops.get("targetBranch", "main"),
            title=f"Roll out {ctx.repo_ref.name} {tag}",
            body=f"Automated rollout by Jarvis (WorkItem `{ctx.workitem['metadata']['name']}`).",
        )
        return pr.url
    finally:
        await forge.aclose()


def _set_kustomize_tag(kustomization: Path, tag: str) -> None:
    if not kustomization.is_file():
        raise AgentFailure(
            reason="KustomizationMissing",
            message=f"{kustomization} not found",
            retryable=False,
        )
    doc = yaml.safe_load(kustomization.read_text()) or {}
    images = doc.setdefault("images", [])
    if images:
        for image in images:
            image["newTag"] = tag
    else:
        raise AgentFailure(
            reason="NoImagesEntry",
            message="kustomization.yaml has no images: list to pin",
            retryable=False,
        )
    kustomization.write_text(yaml.safe_dump(doc, sort_keys=False))


def _set_helm_values_tag(values: Path, tag: str) -> None:
    if not values.is_file():
        raise AgentFailure(reason="ValuesMissing", message=f"{values} not found", retryable=False)
    doc = yaml.safe_load(values.read_text()) or {}
    image = doc.get("image")
    if not isinstance(image, dict) or "tag" not in image:
        raise AgentFailure(
            reason="NoImageTag",
            message="values.yaml has no image.tag to pin",
            retryable=False,
        )
    image["tag"] = tag
    values.write_text(yaml.safe_dump(doc, sort_keys=False))


async def _fix_configuration(ctx: AgentContext, gitops: dict) -> AgentResultEnvelope:
    """Misconfiguration path: let the model edit the gitops manifests directly,
    then open a PR (never DirectPush for config changes)."""
    token = gitops_token()
    workdir = Path(tempfile.mkdtemp(prefix="jarvis-gitops-")) / "repo"
    branch = gitops.get("targetBranch", "main")
    gitx.clone(gitops["repoUrl"], workdir, token=token, branch=branch)
    gitx.configure_identity(workdir)
    editor = RepoEditor(workdir)

    status = ctx.workitem.get("status", {})
    analysis = status.get("analysis") or {}

    class ConfigFix(BaseModel):
        description: str
        commit_message: str

    agent = Agent(
        build_model(ctx.model),
        output_type=ConfigFix,
        instructions=(
            "You fix a deployment misconfiguration in a GitOps repository"
            f" (manifests under {gitops['path']}). Make the minimal manifest"
            " change that resolves the issue; do not touch unrelated apps."
        ),
        tools=[editor.read_file, editor.list_dir, editor.grep, editor.write_file, editor.edit_file],
    )
    title = ctx.workitem["spec"]["source"].get("issue", {}).get("title", "")
    result = await agent.run(
        f"Issue: {title}\nAnalyzer summary: {analysis.get('summary', '')}\n"
        f"Start under {gitops['path']}/."
    )

    if not gitx.run_git(["status", "--porcelain"], cwd=workdir).strip():
        return success(
            AgentStage.SRE,
            {"decision": "NotRequired", "reason": "no configuration change was needed"},
        )

    wi_name = ctx.workitem["metadata"]["name"]
    pr_branch = f"jarvis/configfix-{wi_name}"
    gitx.run_git(["checkout", "-b", pr_branch], cwd=workdir)
    gitx.run_git(["add", "-A"], cwd=workdir)
    gitx.run_git(["commit", "-m", result.output.commit_message], cwd=workdir)
    gitx.run_git(["push", "-u", "origin", pr_branch], cwd=workdir, token=token)
    pr_url = await _open_gitops_pr(ctx, gitops, pr_branch, "config-fix")

    return success(
        AgentStage.SRE,
        {
            "decision": "Required",
            "reason": result.output.description[:300],
            "gitopsPrUrl": pr_url,
            "argocdApp": gitops.get("argocdApp", ""),
        },
    )
