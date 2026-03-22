# Raspberry Pi Setup

## Hardware & OS

| Property | Value |
|----------|-------|
| **Hardware** | Raspberry Pi |
| **OS** | Ubuntu Server 24.04 LTS (arm64) |
| **Hostname** | `chrispi` |
| **Role** | K3s single-node cluster host |

## Initial Setup

### 1. Flash OS

Use **Raspberry Pi Imager** to flash **Ubuntu Server 24.04 LTS (64-bit ARM)**:
- Enable SSH during setup
- Configure WiFi/Ethernet
- Set username and password

### 2. First Boot & System Configuration

```bash
# SSH in via local network
ssh <user>@<pi-ip>

# Update system
sudo apt update && sudo apt upgrade -y

# Set hostname
sudo hostnamectl set-hostname chrispi

# Set timezone
sudo timedatectl set-timezone Europe/Berlin

# Reboot to apply
sudo reboot
```

### 3. SSH Key Authentication

On the **client machine**:

```bash
# Generate SSH key (if not existing)
ssh-keygen -t ed25519 -C "pi-access"

# Copy public key to Pi
ssh-copy-id -i ~/.ssh/id_ed25519.pub <user>@<pi-ip>
```

On the **Pi** — disable password authentication:

```bash
sudo nano /etc/ssh/sshd_config
# Set: PasswordAuthentication no
sudo systemctl restart sshd
```

### 4. SSH Client Config

Add to `~/.ssh/config` on the client:

```
# Local network (direct connection)
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

Usage:
```bash
ssh raspberrypi   # Local network
ssh pi-cf         # Remote (any network)
```

## System Maintenance

### Package Updates

```bash
sudo apt update && sudo apt upgrade -y
```

### System Health

```bash
# CPU, memory, processes
htop

# Disk usage
df -h

# Memory
free -m

# Temperature (Raspberry Pi)
vcgencmd measure_temp
```

### Automatic Security Updates (Optional)

```bash
sudo apt install unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

## Installed Software

| Software | Purpose | Installation |
|----------|---------|-------------|
| K3s | Kubernetes cluster | See [K3s Cluster](k3s-cluster.md) |
| cloudflared | Cloudflare Tunnel | See [Cloudflare Tunnel](cloudflare-tunnel.md) |
| Flux CLI | GitOps management | See [Flux CD](flux-cd.md) |

## Network

| Interface | IP | Purpose |
|-----------|-----|---------|
| Ethernet/WiFi | `192.168.0.168` (local) | Local network access |
| Cloudflare Tunnel | `ssh.chrispicloud.dev` | Remote SSH access |
| Cloudflare Tunnel | `*.chrispicloud.dev` | Web services |

No inbound ports are open on the router. All external access is through the outbound Cloudflare Tunnel.
