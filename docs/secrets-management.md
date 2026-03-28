# Secrets Management

## Overview

Kubernetes Secrets are created **manually** on the cluster and are **not stored in git**. Each namespace has its own set of secrets.

## Current Approach

Secrets are created via `kubectl create secret` directly on the Pi. This is simple and works for a single-operator homelab. For production-grade secrets management, consider migrating to Sealed Secrets or SOPS (see [Planned Improvements](#planned-improvements)).

## Required Secrets per Application

Each application namespace needs:

### 1. GHCR Image Pull Credentials

Required for pulling private container images from GitHub Container Registry.

```bash
kubectl create secret docker-registry ghcr-credentials \
  --docker-server=ghcr.io \
  --docker-username=<github-user> \
  --docker-password=<github-pat> \
  -n <namespace>
```

The GitHub PAT needs `read:packages` scope.

### 2. Database Credentials

```bash
kubectl create secret generic postgres-credentials \
  --from-literal=POSTGRES_USER=<user> \
  --from-literal=POSTGRES_PASSWORD=<password> \
  --from-literal=POSTGRES_DB=<dbname> \
  -n <namespace>
```

### 3. Application Secrets

Connection strings and other app-specific secrets:

```bash
kubectl create secret generic app-secrets \
  --from-literal=ConnectionStrings__DefaultConnection="Host=postgres;Port=5432;Database=<db>;Username=<user>;Password=<password>" \
  -n <namespace>
```

## Finance Tracker Secrets

### Dev Namespace (`financetracker-dev`)

```bash
kubectl create secret docker-registry ghcr-credentials \
  --docker-server=ghcr.io \
  --docker-username=dreyssechris \
  --docker-password=<github-pat> \
  -n financetracker-dev

kubectl create secret generic postgres-credentials \
  --from-literal=POSTGRES_USER=ft_dbadmin \
  --from-literal=POSTGRES_PASSWORD=<password> \
  --from-literal=POSTGRES_DB=financedb_dev \
  -n financetracker-dev

kubectl create secret generic app-secrets \
  --from-literal=ConnectionStrings__DefaultConnection="Host=postgres;Port=5432;Database=financedb_dev;Username=ft_dbadmin;Password=<password>" \
  -n financetracker-dev
```

### Prod Namespace (`financetracker-prod`)

Same structure with `financedb_prod` as database name.

## Bachelor-Demo Secrets (`bachelor-demo`)

```bash
kubectl create secret generic mariadb-credentials \
  --from-literal=MARIADB_ROOT_PASSWORD=<root-password> \
  --from-literal=MYSQL_PASSWORD=<matomo-password> \
  --from-literal=MYSQL_DATABASE=matomo \
  --from-literal=MYSQL_USER=matomo \
  --from-literal=MATOMO_DATABASE_USERNAME=matomo \
  --from-literal=MATOMO_DATABASE_PASSWORD=<matomo-password> \
  --from-literal=MATOMO_DATABASE_DBNAME=matomo \
  -n bachelor-demo

kubectl create secret generic grafana-credentials \
  --from-literal=GF_SECURITY_ADMIN_PASSWORD=<grafana-password> \
  -n bachelor-demo

kubectl create secret docker-registry ghcr-credentials \
  --docker-server=ghcr.io \
  --docker-username=dreyssechris \
  --docker-password=<github-pat> \
  -n bachelor-demo
```

## Managing Secrets

```bash
# List secrets in a namespace
kubectl get secrets -n <namespace>

# View secret details (base64 encoded)
kubectl get secret <name> -n <namespace> -o yaml

# Decode a secret value
kubectl get secret <name> -n <namespace> -o jsonpath='{.data.<key>}' | base64 -d

# Delete and recreate (to update)
kubectl delete secret <name> -n <namespace>
kubectl create secret ...

# Or patch a single value
kubectl patch secret <name> -n <namespace> \
  -p '{"data":{"key":"'$(echo -n "new-value" | base64)'"}}'
```

## Secrets in Deployments

Secrets are referenced in K8s manifests via `envFrom` or `env.valueFrom`:

```yaml
# From Secret as environment variables
envFrom:
  - secretRef:
      name: app-secrets

# Single key from Secret
env:
  - name: POSTGRES_PASSWORD
    valueFrom:
      secretKeyRef:
        name: postgres-credentials
        key: POSTGRES_PASSWORD
```

## Security Notes

- Secrets are base64 encoded in K8s, **not encrypted at rest** (by default)
- Anyone with `kubectl` access to the namespace can read secrets
- Never commit secrets to git — use `kubectl create secret` on the cluster
- Use separate passwords for dev and prod
- Rotate GitHub PATs periodically

## Planned Improvements

| Approach | Description | Complexity |
|----------|-------------|-----------|
| **Sealed Secrets** | Encrypt secrets in git, decrypted by a cluster-side controller | Medium |
| **SOPS + age** | Encrypt secret files with age keys, decrypt during apply | Medium |
| **External Secrets** | Sync from external vault (e.g., Vault, AWS SM) | High |

For a homelab, Sealed Secrets or SOPS are the recommended next step. They allow secrets to be stored in git (encrypted) while remaining secure.
