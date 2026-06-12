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
