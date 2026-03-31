# Traefik Ingress

## Overview

**Traefik** is the built-in ingress controller in K3s. It routes external HTTP traffic to Kubernetes services based on hostnames and path prefixes.

## How Traffic Flows

```
Cloudflare Tunnel → cloudflared → localhost:80 → Traefik → Ingress → K8s Service → Pod
```

Traefik listens on port 80 and uses standard Kubernetes Ingress resources for routing.

## Routing Rules

### Dev Environment (`choam-dev.chrispicloud.dev`)

| Path | Target Service | Description |
|------|---------------|-------------|
| `/api` | `api:8080` | Backend API |
| `/scalar` | `api:8080` | API documentation |
| `/openapi` | `api:8080` | OpenAPI spec |
| `/` | `web:80` | Frontend SPA |

### Prod Environment (`choam.chrispicloud.dev`)

| Path | Target Service | Description |
|------|---------------|-------------|
| `/api` | `api:8080` | Backend API |
| `/` | `web:80` | Frontend SPA |

## Ingress Example

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: choam
  namespace: choam-dev
spec:
  rules:
    - host: choam-dev.chrispicloud.dev
      http:
        paths:
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: api
                port:
                  number: 8080
          - path: /
            pathType: Prefix
            backend:
              service:
                name: web
                port:
                  number: 80
```

No middleware is needed — subdomain-based routing means each service receives requests at their natural root paths.

## Adding a New Service Route

For subdomain-based services (recommended):

1. Create a DNS record for `myservice.chrispicloud.dev` in Cloudflare
2. Add the hostname to the Cloudflare Tunnel config
3. Create a K8s Ingress with the new hostname

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: myservice
spec:
  rules:
    - host: myservice.chrispicloud.dev
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: myservice
                port:
                  number: 8080
```

For path-based routing on an existing subdomain (when the service is part of a larger app):

```yaml
- path: /newpath
  pathType: Prefix
  backend:
    service:
      name: newservice
      port:
        number: 8080
```

## Debugging

```bash
# List all Ingress resources
kubectl get ingress -A

# Describe a specific Ingress
kubectl describe ingress choam -n choam-dev

# List middlewares (if any)
kubectl get middleware -A

# Traefik dashboard (if enabled)
kubectl port-forward -n kube-system deploy/traefik 9000:9000
# Then open http://localhost:9000/dashboard/

# Traefik logs
kubectl logs -n kube-system deploy/traefik
```

## Ingress Types

Traefik supports two ways to define routes. We use both for different reasons:

### Standard Kubernetes Ingress (default)

Used for **HTTP backends** (most services). Portable, simple, sufficient for host and path-based routing.

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: myapp
spec:
  rules:
    - host: myapp.chrispicloud.dev
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: myapp
                port:
                  number: 8080
```

### Traefik IngressRoute CRD (when needed)

Used when standard Ingress can't express the routing — specifically for **HTTPS backends** that require `ServersTransport` (e.g. Kubernetes Dashboard with self-signed certs).

```yaml
apiVersion: traefik.io/v1alpha1
kind: ServersTransport
metadata:
  name: skip-tls
spec:
  insecureSkipVerify: true
---
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: myapp
spec:
  entryPoints:
    - web
  routes:
    - match: Host(`dashboard.chrispicloud.dev`)
      kind: Rule
      services:
        - name: myapp
          port: 443
          scheme: https
          serversTransport: skip-tls
```

**Rule of thumb:** Use standard Ingress unless the backend requires HTTPS, custom headers, or other advanced Traefik features.

## Important Notes

- Traefik matches routes in order of **specificity** (longest prefix first), so `/api` matches before `/`
- TLS is handled by Cloudflare, not Traefik (Traefik receives plain HTTP from the tunnel)
- Traefik is managed by K3s — upgrades happen with K3s upgrades
