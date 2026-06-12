"""Write tools and a guarded command runner for the developer agent.
Extends the read-only RepoReader; everything stays jailed to the checkout."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from jarvis_agents.repotools import RepoReader

COMMAND_ALLOWLIST = {
    "pytest",
    "python",
    "python3",
    "pip",
    "uv",
    "ruff",
    "mypy",
    "npm",
    "npx",
    "pnpm",
    "yarn",
    "node",
    "tsc",
    "eslint",
    "vitest",
    "jest",
    "go",
    "gofmt",
    "golangci-lint",
    "make",
    "cargo",
    "rustc",
    "mvn",
    "gradle",
    "dotnet",
    "ls",
    "cat",
    "head",
    "tail",
    "wc",
    "find",
    "diff",
}
COMMAND_TIMEOUT = 300
MAX_OUTPUT = 16_000


class RepoEditor(RepoReader):
    def write_file(self, path: str, content: str) -> str:
        """Create or overwrite a file with the given content."""
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return f"wrote {len(content)} bytes to {path}"

    def edit_file(self, path: str, old_string: str, new_string: str) -> str:
        """Replace an exact, unique occurrence of old_string with new_string."""
        target = self._resolve(path)
        if not target.is_file():
            return f"ERROR: {path} is not a file"
        text = target.read_text(errors="replace")
        count = text.count(old_string)
        if count == 0:
            return "ERROR: old_string not found — read the file and match exactly"
        if count > 1:
            return (
                f"ERROR: old_string occurs {count} times — provide more context to make it unique"
            )
        target.write_text(text.replace(old_string, new_string, 1))
        return f"edited {path}"

    def run_command(self, command: str) -> str:
        """Run a build/test/lint command inside the repository.

        Plain argv only (no shell operators); the first word must be an
        allowlisted tool such as pytest, npm, go, make.
        """
        try:
            argv = shlex.split(command)
        except ValueError as exc:
            return f"ERROR: cannot parse command: {exc}"
        if not argv:
            return "ERROR: empty command"
        tool = Path(argv[0]).name
        if tool not in COMMAND_ALLOWLIST:
            return f"ERROR: {tool!r} is not allowlisted ({', '.join(sorted(COMMAND_ALLOWLIST))})"
        if any(ch in command for ch in ["|", ">", "<", ";", "&", "`", "$("]):
            return "ERROR: shell operators are not supported; run one plain command"
        try:
            result = subprocess.run(
                argv,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=COMMAND_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return f"ERROR: command timed out after {COMMAND_TIMEOUT}s"
        except FileNotFoundError:
            return f"ERROR: {tool} is not installed in this image"
        output = (result.stdout + "\n" + result.stderr).strip()
        if len(output) > MAX_OUTPUT:
            output = output[:MAX_OUTPUT] + "\n…[output truncated]"
        return f"exit code: {result.returncode}\n{output}"
