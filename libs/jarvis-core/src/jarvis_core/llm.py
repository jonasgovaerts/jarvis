"""Pydantic AI model factory wired to the LiteLLM proxy.

Every agent talks OpenAI-compatible to LiteLLM; the proxy owns provider
routing and keys. Model names are LiteLLM logical names ("claude-sonnet").
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

LLM_KEY_FILE = Path("/var/run/secrets/jarvis/llm/key")


def resolve_api_key() -> str:
    """Mounted virtual key in-cluster; env for local runs."""
    if LLM_KEY_FILE.exists():
        return LLM_KEY_FILE.read_text().strip()
    return os.getenv("LLM_API_KEY", "local-dev")


def build_model(model_name: str | None = None, base_url: str | None = None) -> OpenAIChatModel:
    return OpenAIChatModel(
        model_name or os.getenv("JARVIS_MODEL", "claude-sonnet"),
        provider=OpenAIProvider(
            base_url=(base_url or os.getenv("LLM_BASE_URL", "http://localhost:4000")) + "/v1",
            api_key=resolve_api_key(),
        ),
    )
