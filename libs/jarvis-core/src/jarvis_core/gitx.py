"""Git plumbing for agents. Tokens go through GIT_ASKPASS — never in URLs,
argv, or .git/config."""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
from pathlib import Path

from jarvis_core.envelope import AgentFailure


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


def run_git(args: list[str], cwd: Path | None = None, token: str = "") -> str:
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
