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
  --repository=homelab \
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
  url: ssh://git@github.com/dreyssechris/homelab
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

Defined as YAML files in `deploy/k8s/flux/kustomizations/`. Each references a path in this repo and optionally depends on other Kustomizations:

```yaml
# deploy/k8s/flux/kustomizations/financetracker-dev.yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: financetracker-dev
  namespace: flux-system
spec:
  interval: 1m
  path: ./deploy/k8s/apps/finance-tracker/overlays/dev
  sourceRef:
    kind: GitRepository
    name: flux-system
  prune: true
  dependsOn:
    - name: platform    # Ensures namespaces exist first
```

The `platform` Kustomization syncs shared infrastructure (namespaces, dashboard) before app overlays are applied.

## Releasing to Production

Production deployments are triggered by **git tags** on the application repo. The `cd-prod.yml` workflow listens for `v*` tags.

### Create a Release

```bash
cd <app-repo>
git checkout main
git pull

# Tag the current HEAD
git tag v0.3.0
git push origin v0.3.0
```

This triggers the CD pipeline which:
1. Builds ARM64 production images from the tagged commit
2. Pushes them to GHCR with the version tag (e.g. `v0.3.0`)
3. Updates the image tag in `homelab/deploy/k8s/apps/<app>/overlays/prod/kustomization.yaml`
4. Commits and pushes to homelab → Flux deploys automatically

### Useful Tag Commands

```bash
# List all tags
git tag

# Tag a specific commit (not just HEAD)
git tag v0.3.0 <commit-sha>

# Delete a local tag
git tag -d v0.3.0

# Delete a remote tag
git push origin --delete v0.3.0
```

### Versioning Convention

Use [Semantic Versioning](https://semver.org/):
- **v0.x.y** — Pre-release / early development
- **vMAJOR.MINOR.PATCH** — `MAJOR` = breaking changes, `MINOR` = new features, `PATCH` = bug fixes

### Dev vs Prod Flow

| Environment | Trigger | Image Tag |
|-------------|---------|-----------|
| Dev | Push to `main` | `sha-<commit>` (automatic) |
| Prod | Push a `v*` tag | `v0.3.0` (manual) |

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

## Sync Flow

All K8s manifests live in this **homelab** repo. Application repos (e.g. finance-tracker) only contain source code and CI/CD workflows. The CD pipelines update image tags in homelab via cross-repo pushes.

```
homelab (this repo — single source of truth for K8s state)
└── deploy/k8s/
    ├── flux/                          # Flux bootstrap + sync config
    │   └── kustomizations/            # One YAML per sync target
    ├── platform/                      # Shared infra (namespaces, dashboard)
    └── apps/
        └── finance-tracker/
            ├── base/                  # Shared K8s resources
            └── overlays/
                ├── dev/               # Dev config + image tag (auto-updated by CD)
                └── prod/              # Prod config + image tag (updated on v* tag)
```

## Adding a New Application

1. Create manifests under `deploy/k8s/apps/<app>/base/` and `overlays/dev|prod/`
2. Add a Flux Kustomization YAML in `deploy/k8s/flux/kustomizations/`:

```yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: <app>-dev
  namespace: flux-system
spec:
  interval: 1m
  path: ./deploy/k8s/apps/<app>/overlays/dev
  sourceRef:
    kind: GitRepository
    name: flux-system
  prune: true
  dependsOn:
    - name: platform
```

3. Reference it in `deploy/k8s/flux/kustomizations/kustomization.yaml`
4. Add the app's CD workflow to push image tag updates to this repo (requires `HOMELAB_PAT` secret)

See [Adding a Service](adding-a-service.md) for the full checklist.

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
| Wrong image running | Check if CD updated the tag: `git log -- deploy/k8s/apps/<app>/overlays/dev/kustomization.yaml` |
| Resources not pruned | Ensure `prune: true` is set on the Kustomization |
