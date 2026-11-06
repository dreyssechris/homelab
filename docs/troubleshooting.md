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

# k3s datastore health (see "k3s Datastore Bloated or Corrupted")
sudo ls -la /mnt/storage/k3s/server/db/state.db
sudo journalctl -u k3s --since "-1h" | grep -iE "compact|malformed" | tail -3
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

If `k3s-server` itself is the heaviest process (GBs of RSS while the pods use little), the cause is usually the datastore, see the next section.

### k3s Datastore Bloated or Corrupted (Pi Thrashing, API Slow)

**Symptoms**

- Right after a boot the Pi becomes unusable: load in the hundreds, almost no free RAM (there is no swap), SSH logins time out, `kubectl` reports "connection refused" or hangs. `k3s-server` alone holds several GB of RSS.
- While running: many `Slow SQL` lines in the k3s log, Flux controllers with hundreds of restarts (they keep losing leader election), stale IPs in `kubectl get endpoints kubernetes -n default`.

**Check**

```bash
# Size of the kine datastore (healthy: a few MB up to ~100 MB)
sudo ls -la /mnt/storage/k3s/server/db/

# Compaction runs every 5 minutes and must succeed
sudo journalctl -u k3s --since "-1h" | grep -iE "compact|malformed" | tail -5
#   healthy: COMPACT deleted N rows from M revisions ... compacted to X/Y
#   broken:  Compact failed: failed to compact to revision ...: database disk image is malformed
```

**Background**

K3s keeps the cluster state in kine on SQLite (`/mnt/storage/k3s/server/db/state.db`, data dir `/mnt/storage/k3s` on the USB disk). Every update of an object writes a new row (revision), and kine deletes superseded revisions every 5 minutes (compaction). Flux status updates (choam-dev reconciles every minute) and leader election leases produce thousands of revisions per hour, so without working compaction the file grows by gigabytes within weeks. A damaged index, typically after a hard power loss, makes every compaction fail with "database disk image is malformed". Expiring keys (events, the master lease of an old node IP) are then no longer removed either, which is how `192.168.0.168` stayed in the `kubernetes` endpoints after the IP change. At startup the API server loads the whole datastore, which explains the memory spike and the thrashing.

**Repair** (incident 2026-11-06: 1.7 GB with 742k rows down to 5.6 MB with 685 rows; only two indexes were damaged, no data lost)

1. Stop k3s. Containers keep running (`KillMode=process`), so apps behind Traefik usually stay reachable; only the API and the dashboard are down.

   ```bash
   sudo systemctl stop k3s
   ```

2. Back up all three files (`state.db`, `-wal`, `-shm`):

   ```bash
   sudo mkdir -p /mnt/storage/backups/k3s-db-YYYY-MM-DD
   sudo sh -c 'cp -a /mnt/storage/k3s/server/db/state.db* /mnt/storage/backups/k3s-db-YYYY-MM-DD/'
   ```

3. Analyse the backup read-only. Run from the PC in this repo, the script is piped via stdin:

   ```bash
   ssh pi-local "sudo python3 - /mnt/storage/backups/k3s-db-YYYY-MM-DD/state.db" < scripts/kine-db-analyze.py
   ```

   Look at the `integrity_check` result. Messages like "row N missing from index" or "wrong # of entries in index" mean only indexes are damaged and `REINDEX` fixes them. If the full table scan itself fails, table pages are damaged: stop here and restore an older backup or use `sqlite3 .recover` instead.

4. Repair a working copy and verify it against the backup. Optional extra arguments are keys to delete, e.g. the master lease of an old node IP:

   ```bash
   ssh pi-local "sudo mkdir -p /mnt/storage/k3s-repair-YYYY-MM-DD && sudo sh -c 'cp -a /mnt/storage/backups/k3s-db-YYYY-MM-DD/state.db* /mnt/storage/k3s-repair-YYYY-MM-DD/'"
   ssh pi-local "sudo python3 - /mnt/storage/k3s-repair-YYYY-MM-DD/state.db /mnt/storage/backups/k3s-db-YYYY-MM-DD/state.db /registry/masterleases/<old-ip>" < scripts/kine-db-repair.py
   ```

   The script runs `REINDEX`, compacts to the current revision with kine's own query, drops all events and the given keys, runs `VACUUM` and then checks: `integrity_check` ok, revision counter unchanged, every remaining object identical to the backup. On the USB disk this took about 35 minutes for 1.7 GB. Continue only on `RESULT: OK`.

5. Swap the repaired file in and start k3s. Never leave an old `state.db-wal` next to the new file.

   ```bash
   sudo sh -c 'cd /mnt/storage/k3s/server/db && for f in state.db state.db-wal state.db-shm; do [ -e "$f" ] && mv "$f" "$f.broken-YYYY-MM-DD"; done; cp -a /mnt/storage/k3s-repair-YYYY-MM-DD/state.db state.db'
   sudo systemctl start k3s
   ```

6. Verify: `kubectl get nodes`, `kubectl get endpoints kubernetes -n default` (only the current IP), `flux get kustomizations`, `kubectl get pods -A`. Within 5 to 10 minutes the log shows `COMPACT deleted ... rows`. One `mvcc: required revision has been compacted` right after the start is expected.

7. After a few days without problems delete the `*.broken-*` files and the working copy; keep the backup until the next healthy backup exists.

**Prevention:** shut the Pi down cleanly (`sudo shutdown -h now`) instead of cutting power, and after any unplanned power loss check the compaction log line above.

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
| CHOAM API (Dev) | `https://choam-dev.chrispicloud.dev/api/health` | 200 OK |
| CHOAM Web (Dev) | `https://choam-dev.chrispicloud.dev/` | HTML page |
| CHOAM API (Prod) | `https://choam.chrispicloud.dev/api/health` | 200 OK |
| CHOAM Web (Prod) | `https://choam.chrispicloud.dev/` | HTML page |
