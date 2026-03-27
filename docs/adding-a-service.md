# Adding a Service

Blueprint for deploying a new application to the K3s cluster.

## Architecture

All K8s manifests live in this **homelab** repo — application repos only contain source code, Dockerfiles, and CI/CD workflows. The CD pipelines push image tag updates to homelab, and Flux deploys them.

```
Application Repo (e.g. finance-tracker)     Homelab Repo (this repo)
├── src/                                     ├── deploy/k8s/apps/<app>/
├── .github/workflows/                       │   ├── base/
│   ├── ci.yml                               │   └── overlays/dev|prod/
│   ├── cd-dev.yml   ── pushes tag to ──►    │
│   └── cd-prod.yml  ── pushes tag to ──►    ├── deploy/k8s/flux/kustomizations/
└── Dockerfile                               │   └── <app>-dev|prod.yaml
                                             └── deploy/k8s/platform/namespaces.yaml
```

## Prerequisites

- Application repo with a working Dockerfile (ARM64-compatible)
- CI/CD pipeline that builds and pushes images to GHCR
- `HOMELAB_PAT` secret in the app repo (GitHub PAT with repo scope for homelab)

## Step-by-Step

### 1. Add Namespaces

Add new namespaces to `deploy/k8s/platform/namespaces.yaml`:

```yaml
---
apiVersion: v1
kind: Namespace
metadata:
  name: <app>-dev
---
apiVersion: v1
kind: Namespace
metadata:
  name: <app>-prod
```

All namespaces are managed centrally in this file — do not create them in individual manifests.

### 2. Create Secrets

```bash
ssh pi-cf

# GHCR credentials
kubectl create secret docker-registry ghcr-credentials \
  --docker-server=ghcr.io \
  --docker-username=dreyssechris \
  --docker-password=<github-pat> \
  -n <app>-dev

# Database credentials (if applicable)
kubectl create secret generic postgres-credentials \
  --from-literal=POSTGRES_USER=<user> \
  --from-literal=POSTGRES_PASSWORD=<password> \
  --from-literal=POSTGRES_DB=<dbname> \
  -n <app>-dev

# App secrets
kubectl create secret generic app-secrets \
  --from-literal=<KEY>=<value> \
  -n <app>-dev
```

Repeat for `-prod` namespace with production values. See [Secrets Management](secrets-management.md).

### 3. Create K8s Manifests

In this **homelab** repo under `deploy/k8s/apps/<app>/`:

```
deploy/k8s/apps/<app>/
├── base/
│   ├── kustomization.yaml
│   ├── deployment.yaml
│   └── service.yaml
└── overlays/
    ├── dev/
    │   ├── kustomization.yaml
    │   └── ingress.yaml
    └── prod/
        ├── kustomization.yaml
        └── ingress.yaml
```

#### Base Deployment Template

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: <app>
spec:
  replicas: 1
  selector:
    matchLabels:
      app: <app>
  template:
    metadata:
      labels:
        app: <app>
    spec:
      imagePullSecrets:
        - name: ghcr-credentials
      containers:
        - name: <app>
          image: ghcr.io/dreyssechris/<app>:latest
          ports:
            - containerPort: 8080
          resources:
            requests:
              memory: "128Mi"
              cpu: "100m"
            limits:
              memory: "256Mi"
              cpu: "500m"
          readinessProbe:
            httpGet:
              path: /health
              port: 8080
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /health
              port: 8080
            periodSeconds: 30
---
apiVersion: v1
kind: Service
metadata:
  name: <app>
spec:
  selector:
    app: <app>
  ports:
    - port: 8080
      targetPort: 8080
```

#### Base Kustomization

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - deployment.yaml
  - service.yaml
```

#### Overlay Kustomization (Dev)

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: <app>-dev
resources:
  - ../../base
  - ingress.yaml
images:
  - name: ghcr.io/dreyssechris/<app>
    newTag: sha-<initial-commit>
configMapGenerator:
  - name: app-config
    literals:
      - ASPNETCORE_ENVIRONMENT=Development  # or equivalent
```

### 4. Add Ingress

For HTTP backends, use standard Kubernetes Ingress with Traefik annotations:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: <app>
  annotations:
    traefik.ingress.kubernetes.io/router.middlewares: <app>-dev-strip-prefix@kubernetescrd
spec:
  rules:
    - host: dev.chrispicloud.dev
      http:
        paths:
          - path: /<app>
            pathType: Prefix
            backend:
              service:
                name: <app>
                port:
                  number: 8080
---
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: strip-prefix
spec:
  stripPrefix:
    prefixes:
      - /<app>
```

For HTTPS backends (e.g. services with self-signed certs), use Traefik IngressRoute CRD with ServersTransport. See [Traefik Ingress](traefik-ingress.md#ingress-types).

### 5. Add Flux Kustomization

Create `deploy/k8s/flux/kustomizations/<app>-dev.yaml`:

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

Create a matching `<app>-prod.yaml` with `interval: 5m` and the prod overlay path. Reference both in `deploy/k8s/flux/kustomizations/kustomization.yaml`.

### 6. Add Cloudflare Tunnel Route (If New Hostname)

Only needed if the service requires its own hostname (not just a new path under existing hostnames):

1. Add ingress rule to `/etc/cloudflared/config.yml` on the Pi
2. Create a **Tunnel Public Hostname** in Cloudflare Zero Trust (Networks → Tunnels → Public Hostname → Add) — do NOT create manual CNAME records
3. Restart: `sudo systemctl restart cloudflared`

> **Important:** Always use Tunnel Public Hostname routes. Manual CNAME records route traffic to the wrong origin instead of through the tunnel.

See [Cloudflare Tunnel — Adding a New Hostname](cloudflare-tunnel.md#adding-a-new-hostname).

### 7. Set Up CI/CD

In the **application repo**, create GitHub Actions workflows:

- **CI** (`ci.yml`): Lint + build on PRs to main
- **CD Dev** (`cd-dev.yml`): On push to main → build ARM64 image → push to GHCR → update image tag in **homelab** repo
- **CD Prod** (`cd-prod.yml`): On `v*` tag → build → push → update prod tag in **homelab** repo

The CD workflows need `HOMELAB_PAT` secret to push to this repo. See [Flux CD — Releasing to Production](flux-cd.md#releasing-to-production).

Key workflow steps for ARM64 cross-compilation:
```yaml
- uses: docker/setup-qemu-action@v3
- uses: docker/setup-buildx-action@v3
- uses: docker/build-push-action@v6
  with:
    platforms: linux/arm64
    push: true
    tags: ghcr.io/dreyssechris/<app>:sha-${{ github.sha }}
```

### 8. Verify Deployment

```bash
# Check Flux synced
flux get kustomizations

# Check pods
kubectl get pods -n <app>-dev

# Check logs
kubectl logs -f deploy/<app> -n <app>-dev

# Test via URL
curl https://dev.chrispicloud.dev/<app>/health
```

## Checklist

- [ ] Namespaces added to `platform/namespaces.yaml`
- [ ] Secrets created in both namespaces
- [ ] Dockerfile builds for ARM64
- [ ] K8s manifests in `deploy/k8s/apps/<app>/` (base + overlays)
- [ ] Ingress + middleware configured
- [ ] Flux Kustomization YAMLs created and referenced
- [ ] CI/CD workflows with `HOMELAB_PAT` secret
- [ ] Health endpoint responds
- [ ] Accessible via Cloudflare Tunnel URL
