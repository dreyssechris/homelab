# K3s Cluster

## Overview

**K3s** is a lightweight Kubernetes distribution designed for edge/IoT. It runs as a single binary and includes **Traefik** as the default ingress controller.

| Property | Value |
|----------|-------|
| **Type** | Single-node cluster |
| **Host** | Raspberry Pi (arm64) |
| **Ingress** | Traefik (built-in) |
| **GitOps** | Flux CD v2 |

## Installation

```bash
# Install K3s
curl -sfL https://get.k3s.io | sh -

# Verify
sudo k3s kubectl get nodes
```

### Kubeconfig for Non-Root Usage

```bash
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $USER:$USER ~/.kube/config
chmod 600 ~/.kube/config
```

After this, `kubectl` works without `sudo`.

## Namespaces

Namespaces are die logische Trennung im Cluster. Jeder Namespace ist ein isolierter Bereich mit eigenen Pods, Services, Secrets und Ingress-Regeln. Ressourcen in verschiedenen Namespaces können sich nicht gegenseitig sehen (außer explizit konfiguriert).

### K8s System-Namespaces (von K3s automatisch erstellt)

Diese existieren in jedem Kubernetes-Cluster und werden nicht manuell verwaltet:

| Namespace | Was läuft darin | Warum |
|-----------|----------------|-------|
| `kube-system` | Traefik, CoreDNS, local-path-provisioner, metrics-server | K3s-interne Komponenten — Networking, DNS-Auflösung, Ingress, Storage |
| `kube-node-lease` | Node-Heartbeats | K8s prüft damit ob Nodes noch leben (intern, ignorieren) |
| `kube-public` | Cluster-Info | Öffentlich lesbare Infos (intern, ignorieren) |
| `default` | *(leer)* | Standard-Namespace wenn keiner angegeben wird — wir nutzen ihn nicht |

### Flux-Namespace

| Namespace | Was läuft darin | Warum |
|-----------|----------------|-------|
| `flux-system` | source-controller, kustomize-controller, helm-controller, notification-controller | Flux CD überwacht das Git-Repo und synchronisiert Änderungen auf den Cluster. Eigener Namespace weil Flux sich selbst verwaltet (Bootstrap) |

### Unsere Namespaces (in `platform/namespaces.yaml` deklariert)

| Namespace | Was läuft darin | Warum eigener Namespace |
|-----------|----------------|------------------------|
| `platform` | *(aktuell leer — reserviert für zukünftige shared Services wie Monitoring)* | Trennung von App-spezifischen und plattformweiten Diensten |
| `kubernetes-dashboard` | Dashboard UI + Metrics Scraper | Dashboard hat eigene RBAC-Regeln und ServiceAccounts — Isolation vom Rest |
| `choam-dev` | API + Web + PostgreSQL (Dev-Versionen) | Dev-Umgebung mit eigenen Secrets, eigenen Image-Tags (sha-Commits), eigener DB |
| `choam-prod` | API + Web + PostgreSQL (Prod-Versionen) | Prod-Umgebung mit eigenen Secrets, stabilen Image-Tags (v0.2.1), eigener DB |
| `bachelor-demo` | Portal + Matomo + Grafana + MariaDB | Bachelor-Projekt (Webanalyse-Plattform), on-demand — standardmäßig suspended. Siehe [bachelor-demo.md](bachelor-demo.md) |

### Warum Dev und Prod getrennt?

Dev und Prod laufen auf dem gleichen Cluster aber in **komplett isolierten Namespaces**:
- Eigene Datenbanken — Dev-Daten beeinflussen Prod nicht
- Eigene Secrets — Dev und Prod können unterschiedliche DB-Passwörter haben
- Eigene Image-Tags — Dev bekommt jeden Commit (`sha-...`), Prod nur getaggte Releases (`v0.2.1`)
- Eigene Ingress-Regeln — Dev unter `dev.chrispicloud.dev`, Prod unter `chrispicloud.dev`

So kann ein neuer Feature-Branch auf Dev getestet werden, ohne dass Prod betroffen ist.

### Was läuft wo? (Gesamtübersicht)

```
kubectl get pods -A

kube-system            traefik-...              # Ingress Controller (HTTP Routing)
kube-system            coredns-...              # Cluster-internes DNS
kube-system            local-path-provisioner   # Speicher für PVCs
kube-system            metrics-server-...       # Resource-Metriken (kubectl top)

flux-system            source-controller        # Überwacht Git-Repos
flux-system            kustomize-controller     # Wendet Kustomize-Manifeste an
flux-system            helm-controller          # Helm Chart Support
flux-system            notification-controller  # Webhooks / Alerts

kubernetes-dashboard   kubernetes-dashboard     # Web UI für Cluster-Übersicht
kubernetes-dashboard   dashboard-metrics-...    # Metriken für das Dashboard

choam-dev     postgres-0               # Dev-Datenbank
choam-dev     api-...                  # Dev-Backend (ASP.NET Core)
choam-dev     web-...                  # Dev-Frontend (nginx + SPA)

choam-prod    postgres-0               # Prod-Datenbank
choam-prod    api-...                  # Prod-Backend
choam-prod    web-...                  # Prod-Frontend

bachelor-demo          portal-...               # Statische Website (nginx)
bachelor-demo          matomo-...               # Analytics (PHP-FPM + nginx Sidecar)
bachelor-demo          grafana-...              # Dashboards
bachelor-demo          mariadb-0                # Datenbank
                       (nur aktiv wenn manuell eingeschaltet)
```

### Namespace-Verwaltung

Unsere Namespaces sind deklarativ in `deploy/k8s/platform/namespaces.yaml` definiert und werden von Flux automatisch angelegt. Keine manuelle Erstellung mit `kubectl create namespace` nötig.

## Cluster Management

### Status Commands

```bash
# Node status
kubectl get nodes

# All pods across all namespaces
kubectl get pods -A

# Pods in a specific namespace
kubectl get pods -n choam-dev

# Services
kubectl get svc -A

# Ingress routes
kubectl get ingressroute -A

# Resource usage
kubectl top nodes
kubectl top pods -A
```

### K3s Service

```bash
# Status
sudo systemctl status k3s

# Restart
sudo systemctl restart k3s

# Logs
sudo journalctl -u k3s -f

# K3s is enabled on boot by default
sudo systemctl is-enabled k3s
```

### Upgrading K3s

```bash
# Install latest version (same command as initial install)
curl -sfL https://get.k3s.io | sh -

# Verify version
kubectl version --short
```

K3s performs a rolling upgrade. Pods are rescheduled automatically.

## Resource Limits

The Raspberry Pi has limited resources. All deployments should specify resource requests and limits:

| Resource | Guideline |
|----------|-----------|
| **CPU** | Request 50-100m, Limit 200-500m per pod |
| **Memory** | Request 32-256Mi, Limit 64-512Mi per pod |

Monitor usage with:
```bash
kubectl top pods -A
htop  # system-level
```

## Storage

K3s uses the **local-path** storage provisioner by default. PersistentVolumeClaims are backed by local disk.

```bash
# Check PVCs
kubectl get pvc -A

# Check PVs
kubectl get pv
```

Data is stored at `/var/lib/rancher/k3s/storage/` on the Pi.

## Included Components

K3s bundles these by default:

| Component | Purpose |
|-----------|---------|
| **containerd** | Container runtime |
| **Traefik** | Ingress controller (see [Traefik Ingress](traefik-ingress.md)) |
| **CoreDNS** | Cluster DNS |
| **local-path-provisioner** | Storage provisioner |
| **Flannel** | CNI (container networking) |

## Uninstalling K3s

```bash
/usr/local/bin/k3s-uninstall.sh
```

This removes K3s, all Kubernetes resources, and all stored data. Use with extreme caution.
