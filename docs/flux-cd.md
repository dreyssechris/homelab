# Flux CD (GitOps)

## Overview

**Flux CD v2** is the GitOps operator that keeps the K3s cluster in sync with git repositories. When Kubernetes manifests change in a repo, Flux detects the diff and applies the changes automatically.

## How It Works

```
Developer pushes code
        │
        ▼
GitHub Actions (CI/CD)
  → Builds ARM64 images → pushes to GHCR
  → Updates image tag in kustomization.yaml → git push
        │
        ▼  (within 1 minute)
Flux detects change in GitRepository
        │
        ▼
Flux renders Kustomize overlays
        │
        ▼
K3s applies updated manifests → pulls new images → restarts pods
```

No manual `kubectl apply` is needed. The git repo is the single source of truth.

## Installation

### Install Flux CLI

```bash
curl -s https://fluxcd.io/install.sh | sudo bash
```

### Bootstrap Flux

```bash
export GITHUB_TOKEN=<personal-access-token>

flux bootstrap github \
  --owner=dreyssechris \
  --repository=finance-tracker \
  --branch=main \
  --path=deploy/k8s/flux \
  --personal
```

This:
1. Installs Flux controllers in `flux-system` namespace
2. Creates a deploy key on the GitHub repo
3. Creates GitRepository and Kustomization resources
4. Commits Flux manifests to `deploy/k8s/flux/`

## Flux Resources

### GitRepository Source

Tells Flux which repo to watch:

```yaml
apiVersion: source.toolkit.fluxcd.io/v1
kind: GitRepository
metadata:
  name: flux-system
spec:
  url: ssh://git@github.com/dreyssechris/finance-tracker
  ref:
    branch: main
  interval: 1m
  secretRef:
    name: flux-system  # SSH deploy key
```

### Kustomization (Sync Target)

Tells Flux which path to apply:

```yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: flux-system
spec:
  sourceRef:
    kind: GitRepository
    name: flux-system
  path: ./deploy/k8s/flux
  interval: 10m
  prune: true
```

### Application Kustomizations

Created via CLI for each environment:

```bash
# Dev environment
flux create kustomization financetracker-dev \
  --source=flux-system \
  --path="deploy/k8s/overlays/dev" \
  --prune=true \
  --interval=1m

# Prod environment
flux create kustomization financetracker-prod \
  --source=flux-system \
  --path="deploy/k8s/overlays/prod" \
  --prune=true \
  --interval=1m
```

## Management Commands

```bash
# Check Flux health
flux check

# List all kustomizations and their sync status
flux get kustomizations

# List git sources
flux get sources git

# Force immediate reconciliation
flux reconcile kustomization financetracker-dev --with-source

# Suspend syncing (for manual debugging)
flux suspend kustomization financetracker-dev

# Resume syncing
flux resume kustomization financetracker-dev
```

## Sync Flow (Per-Application)

Each application repo contains its own K8s manifests:

```
<app-repo>/
└── deploy/k8s/
    ├── base/              # Shared resources
    ├── overlays/dev/      # Dev-specific patches
    ├── overlays/prod/     # Prod-specific patches
    └── flux/              # Flux bootstrap manifests
```

Flux watches the repo and applies the appropriate overlay for each environment.

## Adding a New Repo to Flux

To have Flux watch an additional repository:

```bash
# Create a GitRepository source
flux create source git <repo-name> \
  --url=ssh://git@github.com/dreyssechris/<repo-name> \
  --branch=main \
  --interval=1m

# Create a Kustomization to sync from it
flux create kustomization <repo-name>-dev \
  --source=<repo-name> \
  --path="deploy/k8s/overlays/dev" \
  --prune=true \
  --interval=1m
```

## Troubleshooting

```bash
# Check Flux logs
kubectl logs -n flux-system deploy/source-controller
kubectl logs -n flux-system deploy/kustomize-controller

# Check events
kubectl get events -n flux-system --sort-by='.lastTimestamp'

# See why a kustomization failed
flux get kustomization <name> -o yaml

# Verify deploy key has access
flux get sources git
```

| Problem | Solution |
|---------|----------|
| Kustomization stuck "not ready" | Check `flux get kustomizations` for error, then `flux reconcile` |
| Source not syncing | Verify deploy key: `flux get sources git` |
| Wrong image running | Check if CI updated the tag: `git log -- deploy/k8s/overlays/dev/kustomization.yaml` |
| Resources not pruned | Ensure `prune: true` is set on the Kustomization |
