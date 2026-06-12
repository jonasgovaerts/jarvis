# Build from the repo root: docker build -f services/issue-watcher/Dockerfile .
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

# Resolve dependencies first so the layer caches across source-only changes.
# The whole workspace's pyproject files are needed for lockfile resolution.
COPY pyproject.toml uv.lock ./
COPY libs/jarvis-core/pyproject.toml libs/jarvis-core/
COPY agents/pyproject.toml agents/
COPY services/gateway/pyproject.toml services/gateway/
COPY services/notifier/pyproject.toml services/notifier/
COPY services/issue-watcher/pyproject.toml services/issue-watcher/
COPY services/workspace/pyproject.toml services/workspace/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package jarvis-issue-watcher

COPY libs/jarvis-core/ libs/jarvis-core/
COPY services/issue-watcher/ services/issue-watcher/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package jarvis-issue-watcher

FROM python:3.13-slim-bookworm
RUN groupadd -r jarvis && useradd -r -g jarvis jarvis
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
USER jarvis
EXPOSE 8000
CMD ["uvicorn", "issue_watcher.main:app", "--host", "0.0.0.0", "--port", "8000"]
