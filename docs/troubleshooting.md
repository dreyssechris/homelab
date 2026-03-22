# Troubleshooting

Runbook for diagnosing and resolving common issues on the platform.

## Quick Diagnostics

Run these first to get an overview of platform health:

```bash
ssh pi-cf

# Cluster health
kubectl get nodes
kubectl get pods -A

# Flux sync status
flux get kustomizations

# Tunnel status
sudo systemctl status cloudflared

# System resources
htop
df -h
free -m
```

## Common Issues

### Pod Not Starting

**Symptoms:** Pod in `CrashLoopBackOff`, `ImagePullBackOff`, or `Pending` state.

```bash
# Check pod status
kubectl get pods -n <namespace>

# Describe for events and error details
kubectl describe pod <pod-name> -n <namespace>

# Check logs
kubectl logs <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace> --previous  # previous crash
```

| Status | Likely Cause | Fix |
|--------|-------------|-----|
| `ImagePullBackOff` | GHCR credentials missing/expired or image doesn't exist | Recreate `ghcr-credentials` secret; verify image tag in GHCR |
| `CrashLoopBackOff` | App crashes on startup (bad config, missing env vars, DB unreachable) | Check logs for the error message |
| `Pending` | Insufficient resources or no matching node | Check `kubectl describe pod` for scheduling events |
| `CreateContainerConfigError` | Missing Secret or ConfigMap | Verify all referenced secrets exist in the namespace |

### Database Connection Failed

**Symptoms:** API pod crashes with connection error, "Host=postgres" unreachable.

```bash
# Check if postgres pod is running
kubectl get pods -n <namespace> | grep postgres

# Check postgres logs
kubectl logs statefulset/postgres -n <namespace>

# Verify postgres service exists
kubectl get svc postgres -n <namespace>

# Verify connection string secret
kubectl get secret app-secrets -n <namespace> -o jsonpath='{.data.ConnectionStrings__DefaultConnection}' | base64 -d
```

### Flux Not Syncing

**Symptoms:** New image pushed but old version still running.

```bash
# Check kustomization status
flux get kustomizations

# Check git source
flux get sources git

# Force reconciliation
flux reconcile kustomization <name> --with-source

# Check Flux controller logs
kubectl logs -n flux-system deploy/kustomize-controller
kubectl logs -n flux-system deploy/source-controller
```

| Problem | Fix |
|---------|-----|
| Source shows "auth error" | Deploy key expired — re-bootstrap Flux |
| Kustomization shows "validation failed" | Manifest has YAML errors — check with `kustomize build` locally |
| Stuck on old commit | Force reconcile: `flux reconcile source git flux-system` |

### Cloudflare Tunnel Down

**Symptoms:** Website and SSH unreachable from remote networks. Local network SSH still works.

```bash
# If you can reach the Pi locally:
ssh raspberrypi

# Check tunnel service
sudo systemctl status cloudflared

# Check logs
sudo journalctl -u cloudflared -n 50

# Restart
sudo systemctl restart cloudflared
```

| Problem | Fix |
|---------|-----|
| Service not running | `sudo systemctl start cloudflared` |
| "tunnel credentials file not found" | Re-login: `cloudflared tunnel login`, recreate tunnel |
| "failed to connect to edge" | Internet connection issue on Pi — check `ping 1.1.1.1` |

### SSH "websocket: bad handshake"

**Symptoms:** Cloudflare Access auth succeeds (browser shows "Success") but SSH connection fails.

**Cause:** `cloudflared` is not running on the Pi.

```bash
# Fix: ensure cloudflared is running as systemd service
ssh raspberrypi  # via local network
sudo systemctl status cloudflared
sudo systemctl start cloudflared
sudo systemctl enable cloudflared
```

### Services Not Accessible via URL

**Symptoms:** Browser shows 404 or connection refused at `*.chrispicloud.dev`.

```bash
# Check tunnel is routing to Traefik
sudo systemctl status cloudflared

# Check Traefik IngressRoutes
kubectl get ingressroute -A

# Describe the IngressRoute
kubectl describe ingressroute <name> -n <namespace>

# Check the service exists and has endpoints
kubectl get svc -n <namespace>
kubectl get endpoints -n <namespace>

# Check middlewares
kubectl get middleware -A
```

### Disk Space Full

**Symptoms:** Pods failing to schedule, PVC errors, system slow.

```bash
# Check disk usage
df -h

# Find large directories
sudo du -sh /var/lib/rancher/k3s/agent/containerd/*

# Clean up unused container images
sudo k3s crictl rmi --prune

# Check PVC usage
kubectl get pvc -A
```

### High Memory Usage

```bash
# System overview
free -m
htop

# Per-pod resource usage
kubectl top pods -A

# Identify the heaviest pods
kubectl top pods -A --sort-by=memory
```

If the Pi is consistently under memory pressure, reduce resource limits in deployments or consider fewer replicas.

## Recovery Procedures

### Full Cluster Restart

```bash
sudo systemctl restart k3s
# Wait 1-2 minutes for all pods to reschedule
kubectl get pods -A -w
```

### Rebuild a Namespace

If a namespace is in a bad state:

```bash
# Delete and recreate
kubectl delete namespace <name>
kubectl create namespace <name>

# Recreate secrets (they're not in git!)
# See: docs/secrets-management.md

# Force Flux to resync
flux reconcile kustomization <name> --with-source
```

### If Pi Is Completely Unreachable

1. Physical access or local network access required
2. Power cycle the Pi
3. SSH via local network: `ssh raspberrypi`
4. Check: `sudo systemctl status k3s cloudflared`
5. Restart services if needed

## Health Check URLs

| Service | URL | Expected |
|---------|-----|----------|
| Finance Tracker API (Dev) | `https://dev.chrispicloud.dev/financetracker/api/health` | 200 OK |
| Finance Tracker Web (Dev) | `https://dev.chrispicloud.dev/financetracker/` | HTML page |
| Finance Tracker API (Prod) | `https://chrispicloud.dev/financetracker/api/health` | 200 OK |
| Finance Tracker Web (Prod) | `https://chrispicloud.dev/financetracker/` | HTML page |
