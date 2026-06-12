# Jarvis — umbrella targets. Component dirs own their internals
# (operator/ has its own kubebuilder Makefile once it lands).

.PHONY: help dev-up dev-down dev-gateway dev-notifier dev-issue-watcher dev-workspace \
        lint test fmt codegen codegen-check images google-auth seal backup-sealing-key

help: ## list targets
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-22s %s\n", $$1, $$2}'

# --- local dev -----------------------------------------------------------

dev-up: ## start local infra (NATS + Postgres + LiteLLM)
	docker compose up -d

dev-down: ## stop local infra
	docker compose down

dev-gateway: ## run the gateway with hot reload
	uv run uvicorn gateway.main:app --reload --port 8000 --app-dir services/gateway/src

dev-notifier: ## run the notifier
	uv run python -m notifier.main

dev-issue-watcher: ## run the issue watcher
	uv run python -m issue_watcher.main

dev-workspace: ## run the workspace service
	uv run python -m workspace.main

# --- quality -------------------------------------------------------------

lint: ## ruff + (later: golangci-lint, eslint)
	uv run ruff check .
	uv run ruff format --check .

fmt: ## format everything
	uv run ruff check --fix .
	uv run ruff format .

test: ## run python tests
	uv run pytest -q

# --- contracts -----------------------------------------------------------

codegen: ## pydantic -> JSON Schema -> zod/TS (output is committed)
	uv run python tools/codegen.py
	npm --prefix libs/ts/jarvis-events run generate
	npm --prefix libs/ts/jarvis-events run typecheck

codegen-check: codegen ## fail if generated contracts drifted from the models
	git diff --exit-code schemas/ libs/ts/jarvis-events/src/generated/

# --- images --------------------------------------------------------------

COMPONENTS := gateway notifier issue-watcher workspace agents
images: ## local multi-arch dry-run build of all images (no push)
	for c in $(COMPONENTS); do \
		docker buildx build --platform linux/amd64,linux/arm64 \
			-f $$( [ $$c = agents ] && echo agents || echo services/$$c )/Dockerfile . || exit 1; \
	done

# --- secrets (wired up in the GitOps step) --------------------------------

google-auth: ## one-time Gmail OAuth bootstrap, then seal the token
	uv run --with google-auth-oauthlib python tools/google_auth_bootstrap.py

seal: ## pipe a secret through kubeseal: make seal SECRET=name NS=jarvis-system FILE=secret.yaml
	kubeseal --format yaml < $(FILE)

backup-sealing-key: ## export the sealed-secrets controller key — store in a password manager
	kubectl -n kube-system get secret -l sealedsecrets.bitnami.com/sealed-secrets-key -o yaml
