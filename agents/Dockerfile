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
# The developer/sre agents clone repositories and run the verification gate
# (the target repo's own lint/tests), so the toolchains ship in the image at
# versions matching CI: uv (python), Node 22 (frontend — Vite 7 needs Node
# 20+; Debian's apt node is 18 and too old), Go 1.25 (operator build/vet).
RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
# Node 22 from the official multi-arch image (not Debian's stale apt build).
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22-bookworm-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
# Go toolchain baseline for go build/vet in the gate. GOTOOLCHAIN=auto lets go
# fetch the exact version a target repo's go.mod requires (some need newer than
# this baseline) instead of failing — which previously made the agent "fix" the
# build by downgrading the repo's go.mod.
COPY --from=golang:1.25-bookworm /usr/local/go /usr/local/go
ENV PATH="/usr/local/go/bin:$PATH" \
    GOTOOLCHAIN=auto \
    GOFLAGS=-buildvcs=false
RUN groupadd -r jarvis && useradd -r -m -g jarvis jarvis
WORKDIR /work
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:/usr/local/go/bin:$PATH" \
    GOCACHE=/home/jarvis/.cache/go-build \
    GOPATH=/home/jarvis/go
USER jarvis
ENTRYPOINT ["jarvis-agent"]
