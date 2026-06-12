"""Export the Pydantic contracts to JSON Schema (schemas/) for TS generation.

Run via ``make codegen``. Output is committed; CI fails on drift so the Python
models in jarvis-core stay the single source of truth.

Each model becomes one self-contained schema file ($defs inlined, since the
downstream zod generator handles flat schemas best), plus subjects.json mapping
NATS subject -> payload model name.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jarvis_core import dto, events

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas"

MODELS = [
    events.EventEnvelope,
    *dict.fromkeys(events.SUBJECTS.values()),  # de-dupe, preserve order
    *dto.DTOS,
]


def _inline_defs(node: Any, defs: dict[str, Any]) -> Any:
    """Replace local $refs with their $defs bodies (no recursive models here)."""
    if isinstance(node, dict):
        ref = node.get("$ref", "")
        if ref.startswith("#/$defs/"):
            target = defs[ref.removeprefix("#/$defs/")]
            # Siblings of $ref (e.g. default) merge over the inlined body.
            merged = {
                **_inline_defs(target, defs),
                **{k: v for k, v in node.items() if k != "$ref"},
            }
            return merged
        return {k: _inline_defs(v, defs) for k, v in node.items() if k != "$defs"}
    if isinstance(node, list):
        return [_inline_defs(item, defs) for item in node]
    return node


def main() -> None:
    SCHEMAS_DIR.mkdir(exist_ok=True)
    written: set[str] = set()

    for model in MODELS:
        schema = model.model_json_schema(by_alias=True, mode="serialization")
        defs = schema.get("$defs", {})
        schema = _inline_defs(schema, defs)
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        name = model.__name__
        (SCHEMAS_DIR / f"{name}.json").write_text(json.dumps(schema, indent=2) + "\n")
        written.add(f"{name}.json")

    subjects = {subject: model.__name__ for subject, model in events.SUBJECTS.items()}
    (SCHEMAS_DIR / "subjects.json").write_text(json.dumps(subjects, indent=2) + "\n")
    written.add("subjects.json")

    # Remove schemas for models that no longer exist.
    for stale in SCHEMAS_DIR.glob("*.json"):
        if stale.name not in written:
            stale.unlink()

    print(f"wrote {len(written)} files to {SCHEMAS_DIR.relative_to(REPO_ROOT)}/")


if __name__ == "__main__":
    main()
