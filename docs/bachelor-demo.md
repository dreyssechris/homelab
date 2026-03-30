# Bachelor-Demo: Webanalyse-Plattform auf K8s

Dieses Dokument beschreibt die Architektur und das Infrastrukturkonzept der Bachelor-Demo
(Matomo + Grafana + statische Website) auf dem K8s-Cluster.

## Hintergrund

Das Originalprojekt ([webanalysis](https://github.com/dreyssechris/webanalysis)) ist eine
Docker-Compose-basierte Webanalyse-Plattform (Bachelorarbeit). Es läuft dort mit 6 Containern:
einem Reverse Proxy (nginx mit SSL), Matomo (PHP-FPM + nginx), MariaDB, Grafana und einer
statischen Portal-Website (nginx).

Für das Hosting auf dem K8s-Cluster wurde das Projekt **nicht verändert** — das Originalrepo
mit `docker-compose.yml` bleibt unberührt und kann weiterhin eigenständig gepullt und gestartet
werden. Alle K8s-Manifeste liegen ausschließlich im Homelab-Repo.

## Architektur-Übersicht

```
Internet
  │
  ▼
Cloudflare Tunnel (bachelor-demo.chrispicloud.dev)
  │
  ▼
Traefik Ingress Controller
  │
  ├─ /matomo/*   ──▶  Matomo Service (Pod mit 2 Containern)
  │                      ├─ matomo-nginx  :80  (HTTP → FastCGI)
  │                      └─ matomo-fpm    :9000 (PHP-FPM)
  │
  ├─ /grafana/*  ──▶  Grafana Service :3000
  │
  └─ /*          ──▶  Portal Service :80  (statische HTML-Seite)
                         │
                         ▼
                      MariaDB StatefulSet :3306
                      (wird von Matomo + Grafana genutzt)
```

## Von Docker-Compose zu K8s: Was hat sich geändert?

### 6 Container → 4 Workloads

| Docker-Compose Service | K8s Workload | Was passiert? |
|---|---|---|
| `reverse_proxy` (nginx + SSL) | **Entfällt** | Traefik übernimmt das Routing, Cloudflare die SSL-Terminierung |
| `matomo` (PHP-FPM) + `matomo_web` (nginx) | **1 Deployment** (Sidecar) | Beide Container im selben Pod — nginx leitet an localhost:9000 weiter |
| `db` (MariaDB) | **StatefulSet** | Gleich, aber mit PVC statt Docker Volume |
| `grafana` | **Deployment** | Gleich, mit PVC |
| `portal` (nginx + Volume-Mount) | **Deployment** | Statische Dateien in Container-Image gebacken |

### Warum entfällt der Reverse Proxy?

In Docker-Compose übernimmt der `reverse_proxy`-Container zwei Aufgaben:
1. **SSL-Terminierung** (Let's Encrypt Zertifikate)
2. **Path-basiertes Routing** (`/matomo/` → matomo_web, `/grafana/` → grafana, `/evaschiffmann/` → portal)

Im K8s-Cluster sind diese Aufgaben bereits abgedeckt:
- **SSL**: Cloudflare Tunnel terminiert TLS — der Traffic kommt bereits entschlüsselt im Cluster an
- **Routing**: Traefik Ingress Controller routet anhand der Ingress-Regeln

Ein zusätzlicher nginx-Reverse-Proxy wäre redundant.

## ConfigMaps — wozu?

Es gibt drei ConfigMaps. Sie ersetzen die Volume-Mounts aus `docker-compose.yml`.

### `matomo-nginx` (matomo-nginx-cm.yaml)

**Problem:** Matomo nutzt PHP-FPM. FPM kann keine HTTP-Requests beantworten — es spricht
ausschließlich das FastCGI-Protokoll auf Port 9000. Daher braucht es **immer** einen Webserver
davor, der HTTP in FastCGI übersetzt.

**In Docker-Compose:** Dafür gibt es den separaten `matomo_web`-Container mit der `matomo.conf`:
```
fastcgi_pass matomo:9000;  ← über Docker-Netzwerk zum matomo-Container
```

**In K8s (Sidecar-Pattern):** Beide Container laufen im selben Pod und teilen sich `localhost`.
Die ConfigMap enthält die angepasste nginx-Konfiguration:
```
fastcgi_pass localhost:9000;  ← im selben Pod, kein Netzwerk-Hop
```

### `matomo-config` (matomo-config-cm.yaml)

Enthält die `config.ini.php` — Matomos zentrale Konfigurationsdatei. Anpassungen für K8s:
- `host = "mariadb"` (statt `"db"` — Service-Name im Cluster)
- `trusted_hosts[] = "bachelor-demo.chrispicloud.dev"` (statt duckdns)
- `base_url = "https://bachelor-demo.chrispicloud.dev/matomo/"`

Ohne diese Config würde Matomo die DB nicht finden und Requests von der neuen Domain ablehnen.

### `mariadb-init` (mariadb-init-cm.yaml)

Enthält das SQL-Script `create-read-only-user.sql`, das den `grafana_read`-User anlegt.
MariaDB führt alles in `/docker-entrypoint-initdb.d/` automatisch beim **ersten** Start aus
(wenn die Datenbank noch leer ist).

**In Docker-Compose:** `./mysql-init-scripts:/docker-entrypoint-initdb.d:ro` (Volume-Mount)
**In K8s:** ConfigMap wird an den gleichen Pfad gemountet.

## Portal-Container — warum ein eigenes Image?

In Docker-Compose wird der `portal/evaschiffmann/`-Ordner direkt per Volume-Mount in den
nginx-Container gemountet. In K8s gibt es keine lokalen Ordner zum Mounten.

**Lösung:** Ein minimales Docker-Image (`Dockerfile.portal` im webanalysis-Repo), das die
statischen HTML-Dateien in ein nginx-Image kopiert:
```dockerfile
FROM nginx:alpine
COPY portal/evaschiffmann/ /usr/share/nginx/html/
COPY nginx/config/portal-k8s.conf /etc/nginx/conf.d/default.conf
```

Die `portal-k8s.conf` enthält `try_files $uri $uri.html $uri/ =404;` für clean URLs
(z.B. `/start` → `start.html`). In Docker-Compose hat der Reverse Proxy diese Umschreibung
übernommen — da dieser in K8s entfällt, muss der Portal-nginx das selbst können.

## Ingress & Routing

Ein einziges Ingress-Objekt mit einer Traefik-Middleware:

| Pfad | Ziel-Service | Middleware | Erklärung |
|---|---|---|---|
| `/matomo/*` | matomo:80 | `strip-matomo` | Entfernt `/matomo`-Prefix, weil Matomo intern auf `/` lauscht |
| `/grafana/*` | grafana:3000 | — | Grafana handhabt Sub-Paths nativ (`GF_SERVER_SERVE_FROM_SUB_PATH=true`) |
| `/*` | portal:80 | — | Catch-all für die statische Website |

**Warum braucht `/matomo` ein strip-prefix, `/grafana` aber nicht?**
- Matomo erwartet Requests auf `/` (z.B. `/index.php`). Wenn der Browser `/matomo/index.php`
  aufruft, muss Traefik das `/matomo` entfernen, bevor es an Matomo weitergeleitet wird.
- Grafana hat eine eingebaute Sub-Path-Unterstützung (`GF_SERVER_SERVE_FROM_SUB_PATH`).
  Es erwartet und verarbeitet `/grafana/*` Requests selbstständig.

## Datenpersistenz

| Daten | Typ | Größe | Überlebt Restart? |
|---|---|---|---|
| MariaDB (Analytics-Daten) | PVC (StatefulSet) | 2 Gi | Ja |
| Matomo `/var/www/html` (Plugins, Cache) | PVC | 1 Gi | Ja |
| Grafana `/var/lib/grafana` (Dashboards) | PVC | 1 Gi | Ja |
| Portal (statische HTML-Dateien) | Im Container-Image | ~19 MB | Ja (unveränderlich) |

PVCs bleiben bestehen, auch wenn Pods auf 0 skaliert werden. Die Daten überleben
Shutdown/Startup-Zyklen — wichtig für den On-Demand-Betrieb.

## On-Demand-Betrieb

Die Demo muss nicht permanent laufen. Mit ~370 Mi RAM-Requests belegt sie Ressourcen,
die der CHOAM oder zukünftige Services nutzen könnten.

### Einschalten (für Demo)
```bash
flux resume ks bachelor-demo
flux reconcile ks bachelor-demo --with-source
kubectl get pods -n bachelor-demo -w   # warten bis alles läuft
```

### Ausschalten (nach Demo)
```bash
# Pods herunterfahren (gibt RAM frei, PVCs bleiben)
kubectl scale deploy matomo grafana portal -n bachelor-demo --replicas=0
kubectl scale sts mariadb -n bachelor-demo --replicas=0
# Flux pausieren (verhindert, dass Flux die Pods wieder hochfährt)
flux suspend ks bachelor-demo
```

### Warum beides (scale + suspend)?

- `scale --replicas=0` allein: Flux würde innerhalb von 10 Minuten die Replicas wieder auf 1 setzen
- `flux suspend` allein: Stoppt nur die Reconciliation, die laufenden Pods bleiben aktiv
- **Beides zusammen:** Pods werden gestoppt UND Flux greift nicht ein

## Secrets

Werden manuell auf dem Cluster erstellt (nicht in Git):

- `mariadb-credentials` — DB-Zugangsdaten (Root-Passwort, Matomo-User/Passwort)
- `grafana-credentials` — Grafana Admin-Passwort
- `ghcr-credentials` — GitHub Container Registry Token (für Portal-Image Pull)

Befehle dafür stehen als Kommentare in `overlays/prod/kustomization.yaml`.

## Ressourcen-Budget

| Komponente | Memory Request | Memory Limit |
|---|---|---|
| MariaDB | 128 Mi | 384 Mi |
| Matomo FPM | 128 Mi | 384 Mi |
| Matomo nginx (Sidecar) | 32 Mi | 64 Mi |
| Grafana | 64 Mi | 256 Mi |
| Portal | 16 Mi | 64 Mi |
| **Gesamt** | **368 Mi** | **1.152 Mi** |

Passt neben CHOAM (~832 Mi Requests) und K3s-System (~700 Mi) ins 4 GB Pi.

## Verzeichnisstruktur

```
deploy/k8s/apps/bachelor-demo/
├── base/
│   ├── kustomization.yaml        # Referenziert alle Base-Ressourcen
│   ├── mariadb.yaml              # StatefulSet + Headless Service + PVC
│   ├── matomo.yaml               # Deployment (FPM + nginx Sidecar) + Service + PVC
│   ├── grafana.yaml              # Deployment + Service + PVC
│   ├── portal.yaml               # Deployment + Service
│   ├── matomo-nginx-cm.yaml      # nginx-Config für den FPM-Sidecar
│   ├── matomo-config-cm.yaml     # Matomo config.ini.php (angepasst für K8s)
│   └── mariadb-init-cm.yaml      # SQL-Init-Script (grafana_read User)
└── overlays/
    └── prod/
        ├── kustomization.yaml    # Setzt Namespace, Image-Tags, Secret-Doku
        └── ingress.yaml          # Traefik Ingress + strip-matomo Middleware
```
