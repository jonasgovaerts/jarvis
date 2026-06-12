# Build from the repo root: docker build -f agents/Dockerfile .
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY libs/jarvis-core/pyproject.toml libs/jarvis-core/
COPY agents/pyproject.toml agents/
COPY services/gateway/pyproject.toml services/gateway/
COPY services/notifier/pyproject.toml services/notifier/
COPY services/issue-watcher/pyproject.toml services/issue-watcher/
COPY services/workspace/pyproject.toml services/workspace/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package jarvis-agents

COPY libs/jarvis-core/ libs/jarvis-core/
COPY agents/ agents/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package jarvis-agents

FROM python:3.13-slim-bookworm
# The developer/sre agents clone repositories and run project tooling.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN groupadd -r jarvis && useradd -r -m -g jarvis jarvis
WORKDIR /work
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
USER jarvis
ENTRYPOINT ["jarvis-agent"]
