# Jarvis

Personal automation platform: an agentic Kubernetes development flow, a kanban-style
dashboard, Gmail automation, and multi-channel notifications — all driven by AI agents
and tracked as Kubernetes custom resources.

```
GitHub issues ──► issue-watcher ──► WorkItem CRs ◄── gateway (chat: feature requests)
                                        │
                                   operator (Go) ── spawns agent Jobs per phase
                                        │            analyzer → developer → devops → sre
                                        ▼
                              NATS JetStream (jarvis.>)
                               ▲        │                    │
        workspace ─────────────┘        ▼                    ▼
        (Gmail poll/classify)      notifier ──► Discord   gateway ──► WS ──► frontend
```

## Components

| Path | What | Stack |
|---|---|---|
| `operator/` | Watches `WorkItem`/`ManagedRepository` CRs, drives the agent pipeline | Go, kubebuilder |
| `agents/` | One image, four stages: `analyzer`, `developer`, `devops`, `sre` | Python, Pydantic AI → LiteLLM |
| `services/gateway` | REST + WebSocket + chat + K8s watcher for the dashboard | Python, FastAPI |
| `services/notifier` | NATS consumer → Discord (channel abstraction) | Python |
| `services/issue-watcher` | Polls GitHub issues → creates WorkItem CRs | Python |
| `services/workspace` | Gmail: classify, label, create tasks, draft replies | Python |
| `frontend/` | Jarvis-style kanban board | React + Vite + TS |
| `libs/jarvis-core` | Shared contracts: events, agent envelope, settings | Python (source of truth) |
| `libs/ts/jarvis-events` | Generated zod schemas / TS types | generated, committed |
| `deploy/` | GitOps source of truth (ArgoCD app-of-apps) | Kustomize + Helm |

## Quickstart (local dev)

```bash
uv sync                 # install the Python workspace
make dev-up             # NATS + Postgres + LiteLLM via docker compose
make lint test          # ruff + pytest
make codegen            # pydantic → JSON Schema → zod/TS (committed; CI checks drift)
```

Services run on the host with hot reload (`make dev-gateway`, ...); only stateful
infrastructure runs in containers. The operator runs against your kubeconfig context
with `make -C operator run`.

## Cluster bootstrap (one-time, manual)

```bash
kubectl config current-context        # MUST be your homelab cluster
kubectl apply -f deploy/argocd/jarvis-root.yaml
make backup-sealing-key               # immediately; store in a password manager
```

Then seal the secrets the apps expect (`make seal`): `litellm-keys` +
`gateway-auth`/`jarvis-db` (jarvis-platform / jarvis-system), `discord-webhook`,
per-repo `repo-token-*` (namespace jarvis), and `gmail-credentials` via
`make google-auth`. ArgoCD tracks `main`; merging `development` → `main`
triggers builds + deploy-bump + sync.

## Conventions

- **Events**: NATS subjects `jarvis.<domain>.<entity>.<verb>`, CloudEvents-lite JSON
  envelope, deterministic `Nats-Msg-Id` for dedupe. Pydantic models in
  `libs/jarvis-core/src/jarvis_core/events.py` are the single source of truth.
- **Agent results**: Job termination-message envelope (`jarvis_core.envelope`), max 4KB;
  large artifacts go to ConfigMaps owned by the WorkItem.
- **Images**: `ghcr.io/jonasgovaerts/jarvis/<component>`, multi-arch (amd64 + arm64),
  tagged `sha-<7>`.
- Only the operator writes WorkItem `.status`. One event publisher per domain.
