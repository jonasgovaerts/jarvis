import json

from jarvis_agents import verify


def _argvs(checks):
    """Drop the workdir, leaving just the argv lists for assertions."""
    return [argv for _wd, argv in checks]


def test_detects_python_checks(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'")
    (tmp_path / "uv.lock").write_text("")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("def test_a(): pass")
    monkeypatch.setattr(verify.shutil, "which", lambda tool: f"/usr/bin/{tool}")

    argvs = _argvs(verify.detect_checks(tmp_path))
    assert ["uv", "run", "ruff", "check", "."] in argvs
    assert ["uv", "run", "pytest", "-q", "-x"] in argvs


def test_detects_npm_scripts_and_installs_when_needed(tmp_path, monkeypatch):
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"lint": "eslint .", "test": "vitest", "build": "tsc"}})
    )
    monkeypatch.setattr(verify.shutil, "which", lambda tool: f"/usr/bin/{tool}")

    argvs = _argvs(verify.detect_checks(tmp_path))
    assert argvs[0] == ["npm", "ci", "--prefer-offline", "--no-audit"]
    assert ["npm", "run", "lint"] in argvs
    assert ["npm", "run", "test", "--", "--run"] in argvs
    assert not any("build" in c for c in argvs)  # only lint/typecheck/test


def test_go_uses_build_and_vet_not_test(tmp_path, monkeypatch):
    (tmp_path / "go.mod").write_text("module x\n\ngo 1.25\n")
    monkeypatch.setattr(verify.shutil, "which", lambda tool: f"/usr/bin/{tool}")

    argvs = _argvs(verify.detect_checks(tmp_path))
    assert ["go", "build", "./..."] in argvs
    assert ["go", "vet", "./..."] in argvs
    # `go test` needs envtest assets the image can't carry — never run it.
    assert not any(c[:2] == ["go", "test"] for c in argvs)


def test_detects_subprojects_in_a_monorepo(tmp_path, monkeypatch):
    # root python workspace + frontend/ node + operator/ go (the jarvis layout)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='root'")
    (tmp_path / "uv.lock").write_text("")
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text(json.dumps({"scripts": {"lint": "x"}}))
    (tmp_path / "operator").mkdir()
    (tmp_path / "operator" / "go.mod").write_text("module op\n\ngo 1.25\n")
    monkeypatch.setattr(verify.shutil, "which", lambda tool: f"/usr/bin/{tool}")

    checks = verify.detect_checks(tmp_path)
    dirs = {wd.name: argv for wd, argv in checks}
    # frontend node check runs in frontend/, go check in operator/
    assert any(wd.name == "frontend" and argv == ["npm", "run", "lint"] for wd, argv in checks)
    assert any(wd.name == "operator" and argv == ["go", "build", "./..."] for wd, argv in checks)
    # python runs once, at the workspace root
    assert sum(1 for wd, argv in checks if argv[:3] == ["uv", "run", "ruff"]) == 1
    assert dirs  # sanity


def test_node_modules_dir_is_not_descended(tmp_path, monkeypatch):
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"lint": "x"}}))
    nm = tmp_path / "node_modules" / "somedep"
    nm.mkdir(parents=True)
    (nm / "package.json").write_text(json.dumps({"scripts": {"lint": "y"}}))
    monkeypatch.setattr(verify.shutil, "which", lambda tool: f"/usr/bin/{tool}")
    # node_modules is skipped, so only the root project is detected. Compare
    # path components relative to root (the tmp_path name itself can contain
    # the substring "node_modules" via the test name).
    checks = verify.detect_checks(tmp_path)
    assert all("node_modules" not in wd.relative_to(tmp_path).parts for wd, _ in checks)


def test_missing_toolchain_detects_nothing(tmp_path, monkeypatch):
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"lint": "x"}}))
    (tmp_path / "go.mod").write_text("module x")
    monkeypatch.setattr(verify.shutil, "which", lambda tool: None)

    assert verify.detect_checks(tmp_path) == []


def test_run_checks_reports_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(
        verify, "detect_checks", lambda root: [(root, ["python3", "-c", "raise SystemExit(1)"])]
    )
    failures = verify.run_checks(tmp_path)
    assert len(failures) == 1
    assert failures[0].command == "python3 -c raise SystemExit(1)"


def test_run_checks_green(tmp_path, monkeypatch):
    monkeypatch.setattr(verify, "detect_checks", lambda root: [(root, ["python3", "-c", "pass"])])
    assert verify.run_checks(tmp_path) == []


def test_run_checks_labels_subproject_dir(tmp_path, monkeypatch):
    sub = tmp_path / "frontend"
    sub.mkdir()
    monkeypatch.setattr(verify, "detect_checks", lambda root: [(sub, ["python3", "-c", "exit(1)"])])
    failures = verify.run_checks(tmp_path)
    assert failures[0].command.startswith("frontend: ")


def test_failed_npm_ci_skips_only_that_dirs_scripts(tmp_path, monkeypatch):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    monkeypatch.setattr(
        verify,
        "detect_checks",
        lambda root: [
            (a, ["npm", "ci", "--prefer-offline", "--no-audit"]),
            (a, ["npm", "run", "lint"]),  # must be skipped after a's ci fails
            (b, ["python3", "-c", "pass"]),  # must still run
        ],
    )

    def fake_run(argv, **kw):
        import subprocess

        rc = 1 if argv[:2] == ["npm", "ci"] else 0
        return subprocess.CompletedProcess(argv, rc, stdout="", stderr="boom" if rc else "")

    monkeypatch.setattr(verify.subprocess, "run", fake_run)
    failures = verify.run_checks(tmp_path)
    # only the npm ci failure is reported; a's lint was skipped, b's check ran
    assert len(failures) == 1
    assert failures[0].command.startswith("a: npm ci")


def test_feedback_format_mentions_command_and_output():
    text = verify.format_feedback([verify.CheckFailure("pytest -q", "E  assert 1 == 2")])
    assert "pytest -q" in text
    assert "assert 1 == 2" in text
    assert "do not delete or weaken" in text
