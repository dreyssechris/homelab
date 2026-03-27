# Adding a Service

Blueprint for deploying a new application to the K3s cluster.

## Prerequisites

- Application repo with a working Dockerfile (ARM64-compatible)
- CI/CD pipeline that builds and pushes images to GHCR
- Flux CD watching the repo (or manifests in an existing watched repo)

## Step-by-Step

### 1. Create Namespaces

```bash
ssh pi-cf

kubectl create namespace <app>-dev
kubectl create namespace <app>-prod
```

### 2. Create Secrets

```bash
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

Repeat for `-prod` namespace with production values.

### 3. Create K8s Manifests

In your application repo:

```
deploy/k8s/
├── base/
│   ├── kustomization.yaml
│   ├── deployment.yaml
│   └── service.yaml
├── overlays/
│   ├── dev/
│   │   ├── kustomization.yaml
│   │   ├── ingress.yaml
│   │   └── middleware.yaml
│   └── prod/
│       ├── kustomization.yaml
│       ├── ingress.yaml
│       └── middleware.yaml
└── flux/
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
  - middleware.yaml
images:
  - name: ghcr.io/dreyssechris/<app>
    newTag: sha-<initial-commit>
configMapGenerator:
  - name: app-config
    literals:
      - ASPNETCORE_ENVIRONMENT=Development  # or equivalent
```

### 4. Add Traefik IngressRoute

```yaml
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: <app>
spec:
  entryPoints:
    - web
  routes:
    - match: Host(`dev.chrispicloud.dev`) && PathPrefix(`/<app>`)
      kind: Rule
      services:
        - name: <app>
          port: 8080
      middlewares:
        - name: strip-<app>
```

### 5. Add Cloudflare Tunnel Route (If New Hostname)

Only needed if the service requires its own hostname (not just a new path under existing hostnames):

1. Add ingress rule to `/etc/cloudflared/config.yml` on the Pi
2. Create a **Tunnel Public Hostname** in Cloudflare Zero Trust (Networks → Tunnels → Public Hostname → Add) — do NOT create manual CNAME records
3. Restart: `sudo systemctl restart cloudflared`

> **Important:** Always use Tunnel Public Hostname routes. Manual CNAME records route traffic to the wrong origin (e.g. Strato IP) instead of through the tunnel.

See [Cloudflare Tunnel — Adding a New Hostname](cloudflare-tunnel.md#adding-a-new-hostname).

### 6. Set Up CI/CD

Create GitHub Actions workflows:

- **CI** (`ci.yml`): Lint + build on PRs
- **CD Dev** (`cd-dev.yml`): Build ARM64 image → push to GHCR → update dev overlay image tag → git push
- **CD Prod** (`cd-prod.yml`): Triggered on git tags → build → push → update prod overlay

Key workflow steps for ARM64 images:
```yaml
- uses: docker/setup-qemu-action@v3
- uses: docker/setup-buildx-action@v3
- uses: docker/build-push-action@v6
  with:
    platforms: linux/arm64
    push: true
    tags: ghcr.io/dreyssechris/<app>:sha-${{ github.sha }}
```

### 7. Bootstrap Flux (If New Repo)

If the manifests are in a new repo (not the finance-tracker repo):

```bash
# Create a new GitRepository source
flux create source git <app> \
  --url=ssh://git@github.com/dreyssechris/<app> \
  --branch=main \
  --interval=1m

# Create Kustomizations for each environment
flux create kustomization <app>-dev \
  --source=<app> \
  --path="deploy/k8s/overlays/dev" \
  --prune=true \
  --interval=1m

flux create kustomization <app>-prod \
  --source=<app> \
  --path="deploy/k8s/overlays/prod" \
  --prune=true \
  --interval=1m
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

- [ ] Namespaces created (dev + prod)
- [ ] Secrets created in both namespaces
- [ ] Dockerfile builds for ARM64
- [ ] K8s manifests (base + overlays)
- [ ] Traefik IngressRoute + middleware
- [ ] CI/CD workflows
- [ ] Flux GitRepository + Kustomizations
- [ ] Health endpoint responds
- [ ] Accessible via Cloudflare Tunnel URL
