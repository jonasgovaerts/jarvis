"""Verification gate for the developer agent.

Detects the repository's lint/test commands (best effort, only for toolchains
present in the agent image) and runs them. Failures are formatted back into
the model loop; the push only happens once everything detected is green.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

CHECK_TIMEOUT = 600
MAX_OUTPUT = 12_000


@dataclass(frozen=True)
class CheckFailure:
    command: str
    output: str


def detect_checks(root: Path) -> list[list[str]]:
    """Lint/test argvs for toolchains that exist both in the repo and image.

    Deliberately language-level (ruff/pytest/npm/go) rather than Makefile
    targets: a Makefile often fans out to toolchains this image doesn't
    carry, which would turn the gate into a permanent red light.
    """
    checks: list[list[str]] = []

    if (root / "pyproject.toml").exists():
        runner = ["uv", "run"] if (root / "uv.lock").exists() and shutil.which("uv") else []
        if runner or shutil.which("ruff"):
            checks.append([*runner, "ruff", "check", "."])
        has_tests = any(root.glob("**/test_*.py")) or any(root.glob("**/*_test.py"))
        if has_tests and (runner or shutil.which("pytest")):
            checks.append([*runner, "pytest", "-q", "-x"])

    package_json = root / "package.json"
    if package_json.exists() and shutil.which("npm"):
        try:
            scripts = json.loads(package_json.read_text()).get("scripts", {})
        except (OSError, ValueError):
            scripts = {}
        if scripts and not (root / "node_modules").exists():
            checks.append(["npm", "ci", "--prefer-offline", "--no-audit"])
        for name in ("lint", "typecheck", "test"):
            if name in scripts:
                args = ["npm", "run", name]
                if name == "test":
                    args += ["--", "--run"]  # vitest et al: no watch mode
                checks.append(args)

    if (root / "go.mod").exists() and shutil.which("go"):
        checks.append(["go", "vet", "./..."])
        checks.append(["go", "test", "./..."])

    return checks


def run_checks(root: Path) -> list[CheckFailure]:
    """Run every detected check; returns the failures (empty == green)."""
    failures: list[CheckFailure] = []
    for argv in detect_checks(root):
        pretty = " ".join(argv)
        log.info("verify: %s", pretty)
        try:
            result = subprocess.run(
                argv, cwd=root, capture_output=True, text=True, timeout=CHECK_TIMEOUT
            )
        except subprocess.TimeoutExpired:
            failures.append(CheckFailure(pretty, f"timed out after {CHECK_TIMEOUT}s"))
            continue
        except FileNotFoundError:
            log.info("verify: %s skipped (tool not in image)", pretty)
            continue
        if result.returncode == 0:
            log.info("verify: %s ✓", pretty)
            continue
        output = (result.stdout + "\n" + result.stderr).strip()
        if len(output) > MAX_OUTPUT:
            output = output[-MAX_OUTPUT:]
        log.info("verify: %s ✗ (exit %d)", pretty, result.returncode)
        failures.append(CheckFailure(pretty, output))
        if argv[:2] == ["npm", "ci"]:
            break  # downstream npm scripts are meaningless without deps
    return failures


def format_feedback(failures: list[CheckFailure]) -> str:
    blocks = [f"### `{f.command}` failed\n```\n{f.output}\n```" for f in failures]
    return (
        "## Verification failed — fix these before the change can ship\n\n"
        + "\n\n".join(blocks)
        + "\n\nFix the underlying problems (do not delete or weaken the checks)."
    )
