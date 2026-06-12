# deploy/ — GitOps source of truth

Synced by ArgoCD on the target cluster. Bootstrap (one-time, manual):

```bash
# 1. Verify you are on the RIGHT cluster context — Jarvis must never target a work cluster.
kubectl config current-context

# 2. Apply the root app (everything else flows from git):
kubectl apply -f deploy/argocd/jarvis-root.yaml

# 3. Immediately back up the sealed-secrets key once the controller is up:
make backup-sealing-key   # store the output in a password manager
```

Layout:

- `argocd/` — app-of-apps children, ordered by sync waves:
  wave 0: sealed-secrets, CNPG operator · wave 1: NATS, LiteLLM, Postgres ·
  wave 2: jarvis operator (CRDs + controller) · wave 3: services + frontend
- `platform/` — config for third-party components (referenced by the Applications;
  charts come from upstream Helm repos, never vendored)
- `apps/<component>/` — kustomize base + `overlays/prod` per jarvis component.
  CI's deploy-bump job pins image tags here with `kustomize edit set image`;
  ArgoCD picks the commit up automatically.

Secrets are SealedSecrets only — plaintext secrets never enter git. Create them with
`make seal` / `make google-auth`.
