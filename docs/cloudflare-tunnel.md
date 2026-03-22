# Cloudflare Tunnel & Remote Access

## Overview

The Raspberry Pi sits behind NAT/CGNAT with no public IP and no open ports. All remote access is provided via **Cloudflare Tunnel**, which establishes an outbound connection from the Pi to Cloudflare's edge network. Combined with **Cloudflare Access (Zero Trust)**, this provides identity-based authentication for all services.

## Architecture

```
Client (MacBook / Browser)
   │
   │  SSH / HTTPS (port 443)
   ▼
Cloudflare Edge (Zero Trust)
   │
   │  Encrypted Tunnel (QUIC)
   ▼
Raspberry Pi
   ├─ Traefik (port 80)  →  K8s Services
   └─ SSHD (port 22)     →  Remote Administration
```

**Key properties:**
- No open inbound ports on the Pi or router
- No public IP or dynamic DNS needed
- TLS termination at Cloudflare edge
- Identity-based access via Cloudflare Access
- Audit logs for all connections

## Why systemd (Not K8s)?

`cloudflared` runs as a **systemd service** on the host, not as a K8s pod. This is intentional:

- Remote SSH access survives K3s failures
- The tunnel is the entry point to K3s — it can't depend on K3s to run
- Simpler lifecycle management (independent of cluster state)

## Exposed Services

| Hostname | Internal Target | Purpose |
|----------|----------------|---------|
| `dev.chrispicloud.dev` | `http://localhost:80` (Traefik) | Dev environment |
| `chrispicloud.dev` | `http://localhost:80` (Traefik) | Prod environment |
| `ssh.chrispicloud.dev` | `ssh://localhost:22` | Remote SSH access |

Traefik handles routing from port 80 to individual K8s services. See [Traefik Ingress](traefik-ingress.md) for routing rules.

## Installation

### Install cloudflared on the Pi

```bash
curl -L --output cloudflared.deb \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
sudo dpkg -i cloudflared.deb
```

### Create Tunnel

```bash
# Authenticate with Cloudflare (opens browser)
cloudflared tunnel login

# Create a named tunnel
cloudflared tunnel create chrispicloud

# This creates:
#   ~/.cloudflared/cert.pem          — Origin certificate (API auth)
#   ~/.cloudflared/<tunnel-id>.json  — Tunnel credentials
```

### Configure Tunnel

Create `~/.cloudflared/config.yml`:

```yaml
tunnel: <tunnel-id>
credentials-file: /home/<user>/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: dev.chrispicloud.dev
    service: http://localhost:80    # Traefik
  - hostname: chrispicloud.dev
    service: http://localhost:80    # Traefik
  - hostname: ssh.chrispicloud.dev
    service: ssh://localhost:22
  - service: http_status:404        # Catch-all fallback
```

### Ingress Rules Explained

| Rule | Protocol | Description |
|------|----------|-------------|
| `dev.chrispicloud.dev` → `http://localhost:80` | HTTP | Forwards to Traefik, which routes to K8s services |
| `chrispicloud.dev` → `http://localhost:80` | HTTP | Same as above, for production namespace |
| `ssh.chrispicloud.dev` → `ssh://localhost:22` | TCP/SSH | Native SSH protocol forwarding (no HTTP) |
| `http_status:404` | — | Catch-all fallback for unknown hostnames |

### Create DNS Records

```bash
cloudflared tunnel route dns chrispicloud dev.chrispicloud.dev
cloudflared tunnel route dns chrispicloud chrispicloud.dev
cloudflared tunnel route dns chrispicloud ssh.chrispicloud.dev
```

This creates CNAME records in Cloudflare DNS pointing to `<tunnel-id>.cfargotunnel.com`.

### Run as systemd Service

```bash
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

The service starts automatically on boot.

### Manage the Service

```bash
# Check status
sudo systemctl status cloudflared

# View logs
sudo journalctl -u cloudflared -f

# Restart
sudo systemctl restart cloudflared
```

## DNS Configuration

| Type | Name | Target |
|------|------|--------|
| CNAME | `dev` | `<tunnel-id>.cfargotunnel.com` |
| CNAME | `@` (root) | `<tunnel-id>.cfargotunnel.com` |
| CNAME | `ssh` | `<tunnel-id>.cfargotunnel.com` |

DNS records point to Cloudflare's tunnel endpoint, not to the Pi's IP address.

## Cloudflare Access (Zero Trust)

### Application

- **Type:** Self-hosted
- **Application Type:** SSH
- **Name:** `remote-ssh-pi`
- **Hostname:** `ssh.chrispicloud.dev`

### Policy

- **Action:** Allow
- **Include:** Email (authorized Cloudflare identity)
- **Session Duration:** Configurable (default: 24h)

This provides:
- MFA-capable authentication
- Session duration control
- Full audit logs of all access attempts

## SSH Remote Access

### How It Works

```
ssh pi-cf
    │
    ├─ SSH client reads ~/.ssh/config
    │  ProxyCommand: cloudflared access ssh --hostname ssh.chrispicloud.dev
    │
    ├─ cloudflared (client-side) connects to Cloudflare edge
    │  → Cloudflare Access checks identity (browser auth on first use)
    │  → Token cached locally for session duration
    │
    ├─ Cloudflare edge forwards via QUIC tunnel to Pi
    │  → cloudflared (server-side) receives the connection
    │  → Forwards to localhost:22
    │
    └─ SSHD authenticates with SSH key
       → Shell session established
```

### Prerequisites (Client)

`cloudflared` must be installed on the client:

```bash
# macOS
brew install cloudflared

# Verify
cloudflared --version
```

### SSH Config (Client)

Add to `~/.ssh/config`:

```
# Local network (direct)
Host raspberrypi
    HostName 192.168.0.168
    User <user>
    IdentityFile ~/.ssh/id_rsa

# Remote via Cloudflare Tunnel
Host pi-cf
    HostName ssh.chrispicloud.dev
    User <user>
    ProxyCommand cloudflared access ssh --hostname %h
    IdentityFile ~/.ssh/id_rsa
    ServerAliveInterval 15
```

### Connecting

```bash
# Remote (from any network)
ssh pi-cf

# Local network (direct, faster)
ssh raspberrypi
```

On first connection via `pi-cf`:
1. A browser window opens for Cloudflare Access login
2. After authentication, a token is issued and cached locally
3. Subsequent connections reuse the cached token until it expires

### Troubleshooting SSH

| Problem | Check |
|---------|-------|
| `cloudflared` not found | `which cloudflared` — install via `brew install cloudflared` |
| Browser login doesn't appear | Check if `cloudflared` version is up to date |
| Connection timeout | Verify tunnel is running on Pi: `sudo systemctl status cloudflared` |
| `websocket: bad handshake` | `cloudflared` not running on the Pi — check systemd service |
| Host key mismatch | `ssh-keygen -R ssh.chrispicloud.dev` to clear old key |
| Token expired | Browser login will re-trigger automatically |

## Credentials

- **`cert.pem`** — Origin certificate for the Tunnel API (created during `cloudflared tunnel login`). Authorizes the host to manage tunnel resources in the Cloudflare account. This is *not* a TLS web certificate.
- **`<tunnel-id>.json`** — Tunnel credentials that authenticate *this specific host* to Cloudflare.

Both files are stored in `~/.cloudflared/` on the Pi.

## Adding a New Hostname

To expose a new service through the tunnel:

1. Add an ingress rule to `~/.cloudflared/config.yml`:
   ```yaml
   - hostname: newservice.chrispicloud.dev
     service: http://localhost:80
   ```

2. Create the DNS record:
   ```bash
   cloudflared tunnel route dns chrispicloud newservice.chrispicloud.dev
   ```

3. Restart the tunnel:
   ```bash
   sudo systemctl restart cloudflared
   ```

4. Add a Traefik IngressRoute in K8s to route the path to the service (if going through Traefik).

## Updating cloudflared

```bash
# On the Pi
curl -L --output cloudflared.deb \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
sudo dpkg -i cloudflared.deb
sudo systemctl restart cloudflared
```

## If Tunnel Is Down

1. SSH via local network if possible: `ssh raspberrypi`
2. Check cloudflared: `sudo systemctl status cloudflared`
3. Check logs: `sudo journalctl -u cloudflared -n 50`
4. Restart: `sudo systemctl restart cloudflared`
5. If credentials are corrupt: re-run `cloudflared tunnel login` and recreate

## Security Properties

- No open inbound ports on the Pi or router
- No direct internet exposure of any service
- Identity-based authentication via Cloudflare Access
- TLS encryption from client to Cloudflare edge
- Encrypted QUIC tunnel from Cloudflare to Pi
- Audit logs and access policies via Cloudflare Zero Trust dashboard
- SSH key authentication required in addition to Cloudflare Access
