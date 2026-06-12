"""Settings base shared by all Jarvis Python services.

Every service subclasses :class:`JarvisSettings`; configuration comes exclusively
from environment variables (locally via ``.env``, in-cluster via Secret/ConfigMap
env), so local and Kubernetes are one code path.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class JarvisSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    service_name: str = "jarvis"
    log_level: str = "INFO"

    nats_url: str = "nats://localhost:4222"

    # LiteLLM proxy (OpenAI-compatible). Agents and services never see provider keys.
    llm_base_url: str = "http://localhost:4000"
    llm_api_key: str = ""
    llm_default_model: str = "claude-sonnet"
