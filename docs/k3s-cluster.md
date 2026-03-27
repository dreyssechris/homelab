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

| Namespace | Purpose |
|-----------|---------|
| `platform` | Shared platform infrastructure |
| `kubernetes-dashboard` | Kubernetes Dashboard UI |
| `financetracker-dev` | Finance Tracker development |
| `financetracker-prod` | Finance Tracker production |
| `flux-system` | Flux CD controllers |
| `kube-system` | K3s system components (Traefik, CoreDNS, etc.) |

### Managing Namespaces

All namespaces are declared in `deploy/k8s/platform/namespaces.yaml` and managed via Flux GitOps — do not create them manually with `kubectl`. Each application gets separate dev and prod namespaces with their own secrets and resources.

## Cluster Management

### Status Commands

```bash
# Node status
kubectl get nodes

# All pods across all namespaces
kubectl get pods -A

# Pods in a specific namespace
kubectl get pods -n financetracker-dev

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
