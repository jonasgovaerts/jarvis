"""Read-only repository tools shared by the analyzer (and reused with write
tools by the developer). All paths are jailed to the checkout root."""

from __future__ import annotations

import re
from pathlib import Path

MAX_FILE_BYTES = 64_000
MAX_MATCHES = 100
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", "dist", "build", "vendor"}


class RepoReader:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def _resolve(self, rel: str) -> Path:
        path = (self.root / rel).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError(f"path escapes the repository: {rel}")
        return path

    def read_file(self, path: str) -> str:
        """Return a file's contents (truncated past 64KB)."""
        target = self._resolve(path)
        if not target.is_file():
            return f"ERROR: {path} is not a file"
        data = target.read_text(errors="replace")
        if len(data) > MAX_FILE_BYTES:
            return data[:MAX_FILE_BYTES] + "\n…[truncated]"
        return data

    def list_dir(self, path: str = ".") -> str:
        """List a directory, marking subdirectories with a trailing slash."""
        target = self._resolve(path)
        if not target.is_dir():
            return f"ERROR: {path} is not a directory"
        entries = []
        for entry in sorted(target.iterdir()):
            if entry.name in SKIP_DIRS:
                continue
            entries.append(entry.name + "/" if entry.is_dir() else entry.name)
        return "\n".join(entries) or "(empty)"

    def grep(self, pattern: str, glob: str = "**/*") -> str:
        """Search files with a regex; returns path:line:text matches."""
        try:
            rx = re.compile(pattern)
        except re.error as exc:
            return f"ERROR: bad regex: {exc}"
        matches: list[str] = []
        for file in self.root.glob(glob):
            if not file.is_file() or any(part in SKIP_DIRS for part in file.parts):
                continue
            try:
                text = file.read_text(errors="replace")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    rel = file.relative_to(self.root)
                    matches.append(f"{rel}:{lineno}:{line.strip()[:200]}")
                    if len(matches) >= MAX_MATCHES:
                        return "\n".join(matches) + "\n…[match limit reached]"
        return "\n".join(matches) or "(no matches)"

    def tree_summary(self, max_entries: int = 200) -> str:
        """Compact top-two-level listing used to seed the prompt."""
        lines: list[str] = []
        for entry in sorted(self.root.iterdir()):
            if entry.name in SKIP_DIRS:
                continue
            if entry.is_dir():
                lines.append(entry.name + "/")
                for child in sorted(entry.iterdir())[:20]:
                    if child.name not in SKIP_DIRS:
                        lines.append(f"  {child.name}" + ("/" if child.is_dir() else ""))
            else:
                lines.append(entry.name)
            if len(lines) >= max_entries:
                lines.append("…")
                break
        return "\n".join(lines)
