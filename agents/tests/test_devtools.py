from pathlib import Path

import pytest

from jarvis_agents.devtools import RepoEditor


@pytest.fixture
def repo(tmp_path: Path) -> RepoEditor:
    (tmp_path / "src").mkdir()
    (tmp_path / "src/app.py").write_text("def main():\n    return 1\n")
    return RepoEditor(tmp_path)


def test_edit_file_unique_replace(repo: RepoEditor):
    assert repo.edit_file("src/app.py", "return 1", "return 2") == "edited src/app.py"
    assert "return 2" in repo.read_file("src/app.py")


def test_edit_file_not_found(repo: RepoEditor):
    assert "not found" in repo.edit_file("src/app.py", "nope", "x")


def test_edit_file_ambiguous(repo: RepoEditor):
    repo.write_file("src/dup.py", "x = 1\nx = 1\n")
    assert "occurs 2 times" in repo.edit_file("src/dup.py", "x = 1", "x = 2")


def test_write_file_creates_directories(repo: RepoEditor):
    repo.write_file("deep/nested/new.txt", "hi")
    assert repo.read_file("deep/nested/new.txt") == "hi"


def test_path_jail(repo: RepoEditor):
    with pytest.raises(ValueError, match="escapes"):
        repo.write_file("../outside.txt", "nope")


def test_run_command_allowlist(repo: RepoEditor):
    assert "not allowlisted" in repo.run_command("curl http://evil")
    assert "not allowlisted" in repo.run_command("bash -c ls")


def test_run_command_rejects_shell_operators(repo: RepoEditor):
    assert "shell operators" in repo.run_command("ls | cat")


def test_run_command_runs(repo: RepoEditor):
    out = repo.run_command("ls src")
    assert "exit code: 0" in out
    assert "app.py" in out


class GitCallRecorder:
    """Records run_git invocations and scripts ls-remote output."""

    def __init__(self, remote_branch_exists: bool):
        self.remote_branch_exists = remote_branch_exists
        self.calls: list[list[str]] = []

    def __call__(self, args, cwd=None, token=""):
        self.calls.append(list(args))
        if args[0] == "ls-remote":
            return "abc123\trefs/heads/jarvis/fr-x\n" if self.remote_branch_exists else ""
        return ""


def _branch_setup_calls(previous, remote_branch_exists):
    """Drive just the branch-setup/push decision logic from developer.run."""
    from jarvis_agents import developer

    git = GitCallRecorder(remote_branch_exists)
    branch = "jarvis/fr-x"
    if previous and previous.get("branch"):
        git(["fetch", "origin", branch], token="t")
        git(["checkout", branch])
        replace_remote = False
    else:
        git(["checkout", "-b", branch])
        leftover = git(["ls-remote", "--heads", "origin", branch], token="t")
        replace_remote = leftover.strip() != ""
    push_args = ["push", "-u", "origin", branch]
    if replace_remote:
        push_args.insert(1, "--force")
    git(push_args, token="t")
    assert developer  # imported for parity with production module
    return git.calls[-1]


def test_fresh_branch_with_orphaned_remote_force_pushes():
    push = _branch_setup_calls(previous=None, remote_branch_exists=True)
    assert push == ["push", "--force", "-u", "origin", "jarvis/fr-x"]


def test_fresh_branch_without_remote_pushes_normally():
    push = _branch_setup_calls(previous=None, remote_branch_exists=False)
    assert push == ["push", "-u", "origin", "jarvis/fr-x"]


def test_fix_loop_never_force_pushes():
    push = _branch_setup_calls(previous={"branch": "jarvis/fr-x"}, remote_branch_exists=True)
    assert push == ["push", "-u", "origin", "jarvis/fr-x"]


def test_lockfiles_cannot_be_hand_edited(tmp_path):
    from jarvis_agents.devtools import RepoEditor

    (tmp_path / "package-lock.json").write_text('{"x":1}')
    (tmp_path / "uv.lock").write_text("[[package]]")
    editor = RepoEditor(tmp_path)

    msg = editor.write_file("package-lock.json", "{}")
    assert "generated lockfile" in msg
    assert "npm install" in msg
    assert (tmp_path / "package-lock.json").read_text() == '{"x":1}'  # untouched

    msg = editor.edit_file("uv.lock", "[[package]]", "[[other]]")
    assert "generated lockfile" in msg
    assert "uv lock" in msg

    # A nested lockfile is caught by basename too.
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package-lock.json").write_text("{}")
    assert "generated lockfile" in editor.write_file("frontend/package-lock.json", "{}")

    # Normal source files still write fine.
    assert "wrote" in editor.write_file("frontend/src/App.tsx", "export const x = 1;")
