"""Git plumbing for agents. Tokens go through GIT_ASKPASS — never in URLs,
argv, or .git/config."""

from __future__ import annotations

import logging
import os
import stat
import subprocess
import tempfile
from pathlib import Path

from jarvis_core.envelope import AgentFailure

log = logging.getLogger(__name__)


def _askpass_env(token: str) -> tuple[dict[str, str], str]:
    fd, path = tempfile.mkstemp(prefix="askpass-", suffix=".sh")
    os.write(fd, b'#!/bin/sh\necho "$JARVIS_GIT_TOKEN"\n')
    os.close(fd)
    os.chmod(path, stat.S_IRWXU)
    env = os.environ | {
        "GIT_ASKPASS": path,
        "JARVIS_GIT_TOKEN": token,
        "GIT_TERMINAL_PROMPT": "0",
    }
    return env, path


# Build artifacts / dependency trees a verification run (npm ci, builds,
# bytecode) drops into the working tree. Never commit these — target repos may
# lack a .gitignore, and a plain `git add -A` once committed node_modules+dist
# as a 359k-line PR with zero feature code in it.
GENERATED_DIRS = (
    "node_modules",
    "dist",
    "build",
    ".next",
    "out",
    "coverage",
    "__pycache__",
    ".venv",
    "venv",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".gradle",
    "target",
)


def stage_all(cwd: Path, token: str = "") -> None:
    """`git add -A` excluding generated/dependency directories (anywhere in the
    tree) via pathspec, so verification byproducts never get committed. Also
    untracks any that a prior attempt already committed."""
    excludes = [f":(glob,exclude)**/{name}/**" for name in GENERATED_DIRS]
    # Drop any generated paths a previous attempt committed (no-op otherwise).
    for name in GENERATED_DIRS:
        run_git(
            ["rm", "-r", "--cached", "--ignore-unmatch", "-q", f":(glob)**/{name}/**"],
            cwd=cwd,
            token=token,
        )
    run_git(["add", "-A", "--", ".", *excludes], cwd=cwd, token=token)


def run_git(args: list[str], cwd: Path | None = None, token: str = "") -> str:
    log.info("git %s", " ".join(args[:6]))
    env, askpass = _askpass_env(token) if token else (dict(os.environ), "")
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
    finally:
        if askpass:
            Path(askpass).unlink(missing_ok=True)
    if result.returncode != 0:
        raise AgentFailure(
            reason="GitCommandFailed",
            message=f"git {args[0]}: {result.stderr.strip()[:500]}",
            retryable=True,
        )
    return result.stdout


def clone(
    repo_url: str,
    dest: Path,
    *,
    token: str,
    depth: int | None = None,
    branch: str | None = None,
) -> Path:
    """Clone over https with the token supplied via askpass. repo_url is the
    plain https URL (https://github.com/owner/name.git)."""
    args = ["clone"]
    if depth:
        args += ["--depth", str(depth)]
    if branch:
        args += ["--branch", branch]
    # Force the username so askpass is only asked for the password.
    url = repo_url.replace("https://", "https://x-access-token@", 1)
    args += [url, str(dest)]
    run_git(args, token=token)
    return dest


def configure_identity(
    repo_dir: Path, name: str = "jarvis-bot", email: str = "jarvis-bot@users.noreply.github.com"
) -> None:
    run_git(["config", "user.name", name], cwd=repo_dir)
    run_git(["config", "user.email", email], cwd=repo_dir)
