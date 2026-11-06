# Homelab: notes for Claude

GitOps source for the chrispicloud K3s cluster on a Raspberry Pi 4 (4 GB RAM, no swap, Ubuntu 24.04,
k3s data dir `/mnt/storage/k3s` on a USB disk). Flux CD syncs `main` of github.com/dreyssechris/homelab:
**every push to `main` is deployed to the Pi.**

## Layout

- `deploy/k8s/flux/kustomizations/`: one Flux Kustomization per app (`platform`, `choam-dev`, `choam-prod`, `ascent`, `bachelor-demo`)
- `deploy/k8s/platform/`: namespaces, Keycloak, Kubernetes dashboard
- `deploy/k8s/apps/<app>/base` + `overlays/<env>`: Kustomize per app
- `docs/`: runbooks (start with `docs/troubleshooting.md`), `scripts/`: helper scripts

## Rules

- Git only with `git -c safe.directory=D:/git-repos/homelab` (otherwise git's dubious ownership check refuses the repo).
- Small commits on a feature branch, never push (a push to `main` deploys). Commit messages in English,
  conventional style as in the history: `feat(app): ...`, `fix(...)`, `docs(...)`, `chore(deploy): ...`.
- Reading is always fine (`kubectl get/describe/logs`, `journalctl`, `ls`). **Ask Chris before any change**
  to the cluster or the Pi: `kubectl apply/patch/delete/scale`, restarting services, reboots, apt upgrades,
  editing files under `/etc` or `/mnt/storage`.
- Workload changes go through Git and Flux, not `kubectl`. Secrets are the exception: created by hand in
  the cluster, never committed (commands in the overlay comments and `docs/secrets-management.md`).
- Files in English, chat with Chris in German.

## Access

- `ssh pi` (Cloudflare tunnel, `ssh.chrispicloud.dev`) or `ssh pi-local` (LAN, 192.168.178.33, DHCP
  reservation in the FritzBox). Passwordless sudo; use `sudo k3s kubectl ...` on the Pi.
- Under heavy load a new SSH login can take minutes: bundle commands into one session.

## Cloudflare tunnel

- Tunnel `financetracker-tunnel` is managed in the Cloudflare dashboard: public hostnames point to
  `http://localhost:80`, Traefik routes by host. The ingress rules in `/etc/cloudflared/config.yml` on the
  Pi are ignored. A new hostname needs a route in the dashboard plus an Ingress in this repo.
- `docs/cloudflare-tunnel.md` and `docs/adding-a-service.md` still describe the old config file way.

## Known pitfalls

- k3s datastore: kine on SQLite, `/mnt/storage/k3s/server/db/state.db`. It must stay small and compaction
  must succeed every 5 minutes. A corrupted index after a power loss bloated it to 1.7 GB in 2026-11
  (runbook: `docs/troubleshooting.md`, "k3s Datastore Bloated or Corrupted").
- The sum of memory limits already exceeds the 4 GB RAM; watch memory before adding workloads.
- The node IP changed in 2026-11 from 192.168.0.168 to 192.168.178.33; the old IP can still show up in docs.
- Hostnames: `choam.chrispicloud.dev`, `choam-dev.chrispicloud.dev`, `auth.chrispicloud.dev` (Keycloak),
  `dashboard.chrispicloud.dev`, `ascent.chrispicloud.dev`. `dev.chrispicloud.dev` does not exist.
- `bachelor-demo` is suspended in Flux on purpose (on demand, `scripts/bachelor-demo-toggle.sh`).
