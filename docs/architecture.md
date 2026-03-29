# Platform Architecture

## Overview

The platform is a single-node **K3s** cluster running on a **Raspberry Pi**, exposed to the internet via a **Cloudflare Tunnel**. It hosts containerized applications deployed through **Flux CD** (GitOps) and routed by **Traefik**.

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Internet                                  │
│                    Client (Browser / SSH)                           │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ HTTPS / SSH
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│              Cloudflare Edge (Zero Trust)                           │
│                                                                     │
│    *.chrispicloud.dev → CNAME → <tunnel-id>.cfargotunnel.com        │
│    TLS termination, Access policies, Audit logs                     │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ Encrypted QUIC Tunnel
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  Raspberry Pi (Ubuntu Server arm64)                 │
│                                                                     │
│   cloudflared (systemd)                                             │
│   ├── dev.chrispicloud.dev            → http://localhost:80 (Traefik) │
│   ├── chrispicloud.dev               → http://localhost:80 (Traefik) │
│   ├── dashboard.chrispicloud.dev     → http://localhost:80 (Traefik) │
│   ├── bachelor-demo.chrispicloud.dev → http://localhost:80 (Traefik) │
│   └── ssh.chrispicloud.dev           → tcp://localhost:22  (SSHD)    │
│                                                                     │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │                     K3s Cluster                             │   │
│   │                                                             │   │
│   │   Traefik Ingress Controller (port 80)                      │   │
│   │   ├── /financetracker/api/* → api:8080                      │   │
│   │   └── /financetracker/*     → web:80                        │   │
│   │                                                             │   │
│   │   ┌─────────────────┐  ┌─────────────────┐                  │   │
│   │   │ financetracker  │  │ financetracker  │                  │   │
│   │   │     -dev        │  │     -prod       │                  │   │
│   │   ├─────────────────┤  ├─────────────────┤                  │   │
│   │   │ web  (nginx)    │  │ web  (nginx)    │                  │   │
│   │   │ api  (ASP.NET)  │  │ api  (ASP.NET)  │                  │   │
│   │   │ db   (Postgres) │  │ db   (Postgres) │                  │   │
│   │   └─────────────────┘  └─────────────────┘                  │   │
│   │                                                             │   │
│   │   ┌─────────────────┐                                        │   │
│   │   │ bachelor-demo   │  (on-demand, suspended by default)    │   │
│   │   ├─────────────────┤                                        │   │
│   │   │ portal (nginx)  │                                        │   │
│   │   │ matomo (fpm+ng) │                                        │   │
│   │   │ grafana         │                                        │   │
│   │   │ db   (MariaDB)  │                                        │   │
│   │   └─────────────────┘                                        │   │
│   │                                                             │   │
│   │   ┌─────────────────┐  ┌─────────────────┐                  │   │
│   │   │ kubernetes-     │  │   flux-system   │                  │   │
│   │   │ dashboard       │  │ Flux CD         │                  │   │
│   │   │ (Web UI)        │  │ controllers     │                  │   │
│   │   └─────────────────┘  └─────────────────┘                  │   │
│   └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

## How the Pieces Fit Together

```
GitHub (finance-tracker repo)              GitHub (homelab repo)
  │                                           │
  │ Push to main / v* tag                     │ CD pushes image tags here
  ▼                                           ▼
GitHub Actions                              Flux CD (on Pi)
  → Builds ARM64 images                      → Watches homelab repo
  → Pushes to GHCR                           → Detects new image tags
  → Updates image tag in homelab repo         → Applies K8s manifests
                                              → Pods restart with new images
```

- **Application repos** (finance-tracker, webanalysis) enthalten nur Source Code, Dockerfiles und CI/CD Workflows
- **Homelab repo** enthält alle K8s-Manifeste und ist die single source of truth für den Cluster-Zustand
- **Flux CD** synchronisiert das homelab repo automatisch auf den Cluster

## Design Principles

1. **GitOps-first** — All deployments are driven by git commits. Flux CD watches the homelab repo and applies changes automatically. No manual `kubectl apply`.

2. **Multi-repo separation** — Infrastructure (homelab) and application code (finance-tracker) live in separate repos. CD pipelines bridge them via cross-repo image tag updates.

3. **Infrastructure independence** — `cloudflared` runs as a systemd service outside K3s, so remote access survives cluster failures.

4. **Namespace isolation** — Each application gets its own dev + prod namespace with dedicated secrets, database, and ingress. See [K3s Cluster — Namespaces](k3s-cluster.md#namespaces) for details.

5. **ARM64-native** — All container images are built for `linux/arm64` via GitHub Actions cross-compilation (QEMU + buildx).

6. **No open ports** — The Pi has no inbound ports open. All external access is through the outbound Cloudflare Tunnel.

7. **Iterative evolution** — Start as a monolith, extract services as complexity grows. Platform services (auth, monitoring) are added incrementally.

## Network Flow

### HTTPS Request (e.g., Finance Tracker)

```
Browser → Cloudflare (TLS) → QUIC Tunnel → cloudflared
  → Traefik (port 80) → IngressRoute match
  → strip /financetracker prefix → K8s Service → Pod
```

### SSH Connection

```
Client → cloudflared access ssh → Cloudflare Access (auth)
  → QUIC Tunnel → cloudflared → localhost:22 → SSHD
```

## Planned Evolution

| Phase | Components | Purpose |
|-------|-----------|---------|
| **Current** | K3s, Traefik, Flux CD, Cloudflare Tunnel | Basic platform with GitOps |
| **Phase 1** | Keycloak | Centralized authentication (OpenID Connect) |
| **Phase 2** | Prometheus, Grafana | Monitoring and dashboards |
| **Phase 3** | Loki | Centralized logging |
| **Phase 4** | RabbitMQ / Redis Streams | Event bus for microservice communication |

Each phase is documented separately as it's implemented. Application repos reference this platform documentation for infrastructure concerns.
