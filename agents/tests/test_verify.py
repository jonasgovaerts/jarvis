import json

from jarvis_agents import verify


def test_detects_python_checks(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'")
    (tmp_path / "uv.lock").write_text("")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("def test_a(): pass")
    monkeypatch.setattr(verify.shutil, "which", lambda tool: f"/usr/bin/{tool}")

    checks = verify.detect_checks(tmp_path)
    assert ["uv", "run", "ruff", "check", "."] in checks
    assert ["uv", "run", "pytest", "-q", "-x"] in checks


def test_detects_npm_scripts_and_installs_when_needed(tmp_path, monkeypatch):
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"lint": "eslint .", "test": "vitest", "build": "tsc"}})
    )
    monkeypatch.setattr(verify.shutil, "which", lambda tool: f"/usr/bin/{tool}")

    checks = verify.detect_checks(tmp_path)
    assert checks[0] == ["npm", "ci", "--prefer-offline", "--no-audit"]
    assert ["npm", "run", "lint"] in checks
    assert ["npm", "run", "test", "--", "--run"] in checks
    assert not any("build" in c for c in checks)  # only lint/typecheck/test


def test_missing_toolchain_detects_nothing(tmp_path, monkeypatch):
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"lint": "x"}}))
    (tmp_path / "go.mod").write_text("module x")
    monkeypatch.setattr(verify.shutil, "which", lambda tool: None)

    assert verify.detect_checks(tmp_path) == []


def test_run_checks_reports_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(
        verify, "detect_checks", lambda root: [["python3", "-c", "raise SystemExit(1)"]]
    )
    failures = verify.run_checks(tmp_path)
    assert len(failures) == 1
    assert failures[0].command == "python3 -c raise SystemExit(1)"


def test_run_checks_green(tmp_path, monkeypatch):
    monkeypatch.setattr(verify, "detect_checks", lambda root: [["python3", "-c", "pass"]])
    assert verify.run_checks(tmp_path) == []


def test_feedback_format_mentions_command_and_output():
    text = verify.format_feedback([verify.CheckFailure("pytest -q", "E  assert 1 == 2")])
    assert "pytest -q" in text
    assert "assert 1 == 2" in text
    assert "do not delete or weaken" in text
