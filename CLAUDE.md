# Jarvis — agent notes

Personal automation platform: GitHub issues flow through an agentic pipeline
(analyzer → developer → devops → sre) driven by a Go operator; a React board
shows everything live; Gmail gets classified into tasks with draft replies.

## Commands

```bash
uv sync                  # Python workspace (libs/jarvis-core, agents, services/*)
make lint test           # ruff + pytest (root), use `make -C operator lint test` for Go
make codegen             # pydantic → schemas/ → zod TS (committed; CI fails on drift)
make dev-up              # NATS + Postgres + LiteLLM via docker compose
make dev-gateway         # gateway with hot reload (FAKE_K8S=true for fixtures)
npm --prefix frontend run dev|lint|typecheck|test|build
make -C operator manifests generate   # after editing api/v1alpha1 types — CI gates drift
```

## Architecture contracts (do not break silently)

- **Event schemas**: `libs/jarvis-core/src/jarvis_core/events.py` is the source
  of truth. `schemas/` + `libs/ts/jarvis-events/src/generated/` are generated
  (make codegen). The operator's Go mirrors live in
  `operator/internal/events/types.go` — keep field names (camelCase) in sync.
- **Agent results**: agents write a ≤4KB JSON envelope to /dev/termination-log
  (`jarvis_core.envelope` ⇄ `operator/internal/jobs/envelope.go`). Result dict
  keys must match the Go json tags of the stage result structs
  (`operator/api/v1alpha1/workitem_types.go`).
- **Single status writer**: only the operator writes WorkItem `.status`.
  Dashboard actions go through the `jarvis.dev/requested-action` annotation
  (approve | retry | cancel).
- **Single event publisher per domain**: operator → `jarvis.workflow.*`,
  gateway → `jarvis.chat.*`/`jarvis.task.*`/draft.approved, workspace →
  `jarvis.email.*`. All publishes carry a deterministic `Nats-Msg-Id`.
- **WorkItem names are deterministic** (`gh-<owner>-<repo>-<n>`, `fr-<hash8>`)
  — creation 409s are the idempotency mechanism, never list-then-create.
- **DB ownership**: workspace owns emails/tasks/gmail_sync_state; gateway owns
  chat/drafts/workflow_events; notifier owns notification_log. Exception:
  gateway updates `tasks.status`. Models in `jarvis_core/db/models.py`.

## Conventions

- Python 3.13, ruff (B008 ignored in api/ routers), pydantic-settings for all
  config (env only — local and in-cluster identical). LLM calls go through the
  LiteLLM proxy with logical model names ("claude-sonnet"), never provider SDKs.
- Operator: kubebuilder layout; retries owned by the operator
  (Job backoffLimit=0); envtest drives Reconcile() directly.
- Images: `ghcr.io/jonasgovaerts/jarvis/<component>`, multi-arch via native
  runners, tag `sha-<7>`; deploy-bump (main only) pins tags in `deploy/`.
- deploy/ is GitOps source of truth (ArgoCD app-of-apps, sync waves 0–3).
  Secrets are SealedSecrets only — never commit plaintext.
- Git tokens never in URLs/argv — `jarvis_core.gitx` uses GIT_ASKPASS.
- Workspace service ships with DRY_RUN=true; flip only after reviewing logged
  decisions against a real inbox.

## Things that look wrong but aren't

- `frontend/Dockerfile` runs `npm ci` inside libs/ts/jarvis-events: the
  file-linked package resolves zod through its own node_modules (real-path
  resolution through the symlink).
- `issue-watcher` RBAC spans two namespaces (SA in jarvis-system, Role in
  jarvis) — its overlay must NOT set a kustomize `namespace:` transformer.
- CI lint for the operator uses `make -C operator lint` because the repo pins
  golangci-lint v2 plus a custom logcheck plugin (the marketplace action
  installs v1 and fails).
