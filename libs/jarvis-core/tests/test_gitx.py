"""stage_all must never commit generated/dependency dirs the verification
gate drops into the tree (node_modules, dist, __pycache__, …)."""

import subprocess
from pathlib import Path

from jarvis_core import gitx


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout


def _init_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    return tmp_path


def _staged(cwd: Path) -> set[str]:
    out = _git(cwd, "diff", "--cached", "--name-only")
    return {line for line in out.splitlines() if line}


def test_stage_all_excludes_generated_dirs(tmp_path):
    repo = _init_repo(tmp_path)
    # real changes
    (repo / "src").mkdir()
    (repo / "src" / "feature.ts").write_text("export const x = 1;\n")
    (repo / "README.md").write_text("# hi\n")
    # generated noise the verify gate / build would create, top-level and nested
    for rel in (
        "node_modules/dep/index.js",
        "frontend/node_modules/dep/index.js",
        "frontend/dist/bundle.js",
        "__pycache__/mod.cpython-313.pyc",
        ".venv/pyvenv.cfg",
    ):
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("generated\n")

    gitx.stage_all(repo)

    assert _staged(repo) == {"src/feature.ts", "README.md"}


def test_stage_all_untracks_previously_committed_generated(tmp_path):
    repo = _init_repo(tmp_path)
    # a prior attempt committed node_modules (the bug we are guarding against)
    (repo / "frontend" / "node_modules").mkdir(parents=True)
    (repo / "frontend" / "node_modules" / "x.js").write_text("old\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "polluted")

    # new round: a real edit plus the dep tree still on disk
    (repo / "app.ts").write_text("export const y = 2;\n")
    gitx.stage_all(repo)
    _git(repo, "commit", "-q", "-m", "clean")

    tracked = _git(repo, "ls-files")
    assert "app.ts" in tracked
    assert "node_modules" not in tracked  # untracked by stage_all
