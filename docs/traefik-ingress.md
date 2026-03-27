# Traefik Ingress

## Overview

**Traefik** is the built-in ingress controller in K3s. It routes external HTTP traffic to Kubernetes services based on hostnames and path prefixes.

## How Traffic Flows

```
Cloudflare Tunnel → cloudflared → localhost:80 → Traefik → IngressRoute → K8s Service → Pod
```

Traefik listens on port 80 and uses **IngressRoute** CRDs (Traefik-specific) for routing.

## Routing Rules

### Dev Environment (`dev.chrispicloud.dev`)

| Path | Target Service | Middleware | Description |
|------|---------------|-----------|-------------|
| `/financetracker/api` | `api:8080` | strip-prefix | Backend API |
| `/financetracker` | `web:80` | strip-prefix | Frontend SPA |
| `/` | `web:80` | redirect-to-app | Redirect to `/financetracker/` |

### Prod Environment (`chrispicloud.dev`)

Same routing rules as dev, different hostname and namespace.

## IngressRoute Example

```yaml
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: financetracker
  namespace: financetracker-dev
spec:
  entryPoints:
    - web
  routes:
    # API: /financetracker/api/* → api:8080 (prefix stripped)
    - match: Host(`dev.chrispicloud.dev`) && PathPrefix(`/financetracker/api`)
      kind: Rule
      services:
        - name: api
          port: 8080
      middlewares:
        - name: strip-financetracker

    # Web: /financetracker/* → web:80 (prefix stripped)
    - match: Host(`dev.chrispicloud.dev`) && PathPrefix(`/financetracker`)
      kind: Rule
      services:
        - name: web
          port: 80
      middlewares:
        - name: strip-financetracker

    # Root: / → redirect to /financetracker/
    - match: Host(`dev.chrispicloud.dev`) && Path(`/`)
      kind: Rule
      services:
        - name: web
          port: 80
      middlewares:
        - name: redirect-to-app
```

## Middlewares

### strip-prefix

Removes the `/financetracker` prefix before forwarding to the service. Both the API and SPA serve from root internally.

```yaml
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: strip-financetracker
spec:
  stripPrefix:
    prefixes:
      - /financetracker
```

### redirect-to-app

Redirects the root path `/` to `/financetracker/`:

```yaml
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: redirect-to-app
spec:
  redirectRegex:
    regex: "^https?://[^/]+/?$"
    replacement: "/financetracker/"
    permanent: false
```

## Adding a New Service Route

1. Create a K8s Service for your application
2. Add an IngressRoute with the appropriate host and path matching
3. Create a strip-prefix middleware if the service serves from root
4. Apply via Flux (commit to git)

Example for a new service at `/newservice`:

```yaml
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: newservice
spec:
  entryPoints:
    - web
  routes:
    - match: Host(`dev.chrispicloud.dev`) && PathPrefix(`/newservice`)
      kind: Rule
      services:
        - name: newservice
          port: 8080
      middlewares:
        - name: strip-newservice
```

## Debugging

```bash
# List all IngressRoutes
kubectl get ingressroute -A

# Describe a specific IngressRoute
kubectl describe ingressroute financetracker -n financetracker-dev

# List middlewares
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

Used for **HTTP backends** (most services). Portable, simple, sufficient for path-based routing with middleware annotations.

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: myapp
  annotations:
    traefik.ingress.kubernetes.io/router.middlewares: <namespace>-strip-prefix@kubernetescrd
spec:
  rules:
    - host: dev.chrispicloud.dev
      http:
        paths:
          - path: /myapp
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

- Traefik matches routes in order of **specificity** (longest prefix first), so `/financetracker/api` matches before `/financetracker`
- Middleware annotations in standard Ingress reference the full namespace-qualified name: `<namespace>-<middleware-name>@kubernetescrd`
- Traefik is managed by K3s — upgrades happen with K3s upgrades
- TLS is handled by Cloudflare, not Traefik (Traefik receives plain HTTP from the tunnel)
