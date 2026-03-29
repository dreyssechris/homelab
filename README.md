# Homelab

Central hub for the **chrispicloud** platform — a personal Kubernetes cluster running on a Raspberry Pi, accessible via Cloudflare Tunnel.

## Platform Overview

| Component | Technology | Status |
|-----------|-----------|--------|
| **Compute** | Raspberry Pi (Ubuntu Server 24.04, arm64) | Active |
| **Orchestration** | K3s (lightweight Kubernetes) | Active |
| **GitOps** | Flux CD v2 | Active |
| **Ingress** | Traefik (K3s built-in) | Active |
| **Remote Access** | Cloudflare Tunnel + Zero Trust | Active |
| **DNS** | Cloudflare (`chrispicloud.dev`) | Active |
| **Auth** | Keycloak (OpenID Connect) | Planned |
| **Monitoring** | Prometheus + Grafana | Planned |
| **Logging** | Loki | Planned |
| **Message Bus** | RabbitMQ | Planned |

## Hosted Services

| Service | Repo | URL | Status |
|---------|------|-----|--------|
| Finance Tracker | [finance-tracker](https://github.com/dreyssechris/finance-tracker) | `dev.chrispicloud.dev/financetracker/` / `chrispicloud.dev/financetracker/` | Always on |
| Bachelor-Demo | [webanalysis](https://github.com/dreyssechris/webanalysis) | `bachelor-demo.chrispicloud.dev` | On-demand |

## Architecture

```
Internet (HTTPS)
      │
Cloudflare Edge (Zero Trust + TLS)
      │
      │  Encrypted QUIC Tunnel
      ▼
Raspberry Pi (Ubuntu Server arm64)
  ├── cloudflared (systemd)        → Tunnel endpoint
  └── K3s Cluster
       ├── Traefik Ingress          → Path-based routing
       ├── Flux CD                  → GitOps controller
       ├── financetracker-dev       → Dev namespace
       ├── financetracker-prod      → Prod namespace
       ├── bachelor-demo            → Bachelor thesis demo (on-demand)
       └── (future namespaces)      → Keycloak, Monitoring, etc.
```

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/architecture.md) | Platform architecture and design decisions |
| [Raspberry Pi Setup](docs/raspberry-pi-setup.md) | Initial Pi setup and OS configuration |
| [K3s Cluster](docs/k3s-cluster.md) | Kubernetes installation and management |
| [Cloudflare Tunnel](docs/cloudflare-tunnel.md) | Remote access, DNS, Zero Trust |
| [Flux CD](docs/flux-cd.md) | GitOps deployment workflow |
| [Traefik Ingress](docs/traefik-ingress.md) | Ingress routing and middlewares |
| [Secrets Management](docs/secrets-management.md) | Kubernetes secrets handling |
| [Adding a Service](docs/adding-a-service.md) | Blueprint for deploying new services |
| [Bachelor-Demo](docs/bachelor-demo.md) | Bachelor thesis webanalysis platform |
| [Troubleshooting](docs/troubleshooting.md) | Runbook for common issues |

## Repository Structure

```
homelab/
├── docs/                              # Platform documentation
│   ├── architecture.md
│   ├── raspberry-pi-setup.md
│   ├── k3s-cluster.md
│   ├── cloudflare-tunnel.md
│   ├── flux-cd.md
│   ├── traefik-ingress.md
│   ├── secrets-management.md
│   ├── adding-a-service.md
│   └── troubleshooting.md
├── deploy/
│   └── k8s/
│       ├── flux/                      # Flux CD bootstrap & sync config
│       │   ├── flux-system/           # Flux controllers (auto-managed)
│       │   └── kustomizations/        # App & platform sync targets
│       │       ├── platform.yaml
│       │       ├── financetracker-dev.yaml
│       │       ├── financetracker-prod.yaml
│       │       └── bachelor-demo.yaml
│       ├── platform/                  # Shared platform infrastructure
│       │   ├── namespaces.yaml        # All cluster namespaces
│       │   └── dashboard/             # Kubernetes Dashboard
│       └── apps/                      # Application manifests
│           ├── finance-tracker/
│           │   ├── base/              # Shared K8s resources
│           │   └── overlays/          # Environment-specific config
│           │       ├── dev/
│           │       └── prod/
│           └── bachelor-demo/
│               ├── base/              # MariaDB, Matomo, Grafana, Portal
│               └── overlays/
│                   └── prod/
└── README.md
```

## Quick Access

```bash
# SSH into Pi (remote, via Cloudflare Tunnel)
ssh pi-cf

# SSH into Pi (local network)
ssh raspberrypi

# Check cluster health
ssh pi-cf 'kubectl get nodes && kubectl get pods -A'

# Check Flux sync
ssh pi-cf 'flux get kustomizations'
```
