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


# Directories never worth descending into for project detection.
_SKIP_DIRS = {
    "node_modules",
    ".venv",
    "venv",
    ".git",
    "vendor",
    "dist",
    "build",
    ".next",
    "target",
}


def _python_checks(d: Path) -> list[list[str]]:
    if not (d / "pyproject.toml").exists():
        return []
    runner = ["uv", "run"] if (d / "uv.lock").exists() and shutil.which("uv") else []
    out: list[list[str]] = []
    if runner or shutil.which("ruff"):
        out.append([*runner, "ruff", "check", "."])
    has_tests = any(d.glob("**/test_*.py")) or any(d.glob("**/*_test.py"))
    if has_tests and (runner or shutil.which("pytest")):
        out.append([*runner, "pytest", "-q", "-x"])
    return out


def _node_checks(d: Path) -> list[list[str]]:
    pj = d / "package.json"
    if not pj.exists() or not shutil.which("npm"):
        return []
    try:
        scripts = json.loads(pj.read_text()).get("scripts", {})
    except (OSError, ValueError):
        scripts = {}
    out: list[list[str]] = []
    if scripts and not (d / "node_modules").exists():
        out.append(["npm", "ci", "--prefer-offline", "--no-audit"])
    for name in ("lint", "typecheck", "test"):
        if name in scripts:
            args = ["npm", "run", name]
            if name == "test":
                args += ["--", "--run"]  # vitest et al: no watch mode
            out.append(args)
    return out


def _go_checks(d: Path) -> list[list[str]]:
    if not (d / "go.mod").exists() or not shutil.which("go"):
        return []
    # build + vet only. `go test ./...` for kubebuilder/k8s repos needs envtest
    # assets (etcd, kube-apiserver) this image can't carry — running it would
    # be a guaranteed false failure. build+vet catches compile and vet errors.
    return [["go", "build", "./..."], ["go", "vet", "./..."]]


def _candidate_dirs(root: Path):
    """The repo root plus its immediate subdirectories — enough to cover the
    common monorepo layout (frontend/, operator/, services/…) without walking
    into dependency trees."""
    yield root
    try:
        children = sorted(p for p in root.iterdir() if p.is_dir())
    except OSError:
        return
    for child in children:
        if child.name not in _SKIP_DIRS and not child.name.startswith("."):
            yield child


def detect_checks(root: Path) -> list[tuple[Path, list[str]]]:
    """(workdir, argv) for each toolchain check found in the root and its
    immediate subdirectories. Python runs once at the shallowest pyproject
    (a uv workspace root covers its members)."""
    checks: list[tuple[Path, list[str]]] = []
    python_done = False
    for d in _candidate_dirs(root):
        py = _python_checks(d)
        if py and not python_done:
            checks.extend((d, c) for c in py)
            python_done = True
        checks.extend((d, c) for c in _node_checks(d))
        checks.extend((d, c) for c in _go_checks(d))
    return checks


def run_checks(root: Path) -> list[CheckFailure]:
    """Run every detected check in its own directory; returns failures."""
    failures: list[CheckFailure] = []
    broken: set[Path] = set()  # dirs whose npm ci failed → skip their scripts
    for workdir, argv in detect_checks(root):
        if workdir in broken:
            continue
        rel = workdir.relative_to(root)
        pretty = " ".join(argv) if str(rel) == "." else f"{rel}: {' '.join(argv)}"
        log.info("verify: %s", pretty)
        try:
            result = subprocess.run(
                argv, cwd=workdir, capture_output=True, text=True, timeout=CHECK_TIMEOUT
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
            broken.add(workdir)  # its scripts would just fail for missing deps
    return failures


def format_feedback(failures: list[CheckFailure]) -> str:
    blocks = [f"### `{f.command}` failed\n```\n{f.output}\n```" for f in failures]
    return (
        "## Verification failed — fix these before the change can ship\n\n"
        + "\n\n".join(blocks)
        + "\n\nFix the underlying problems (do not delete or weaken the checks)."
    )
