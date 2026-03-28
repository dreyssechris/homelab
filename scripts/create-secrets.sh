#!/bin/bash
# ============================================================
# Create all K8s secrets for the homelab cluster.
# Run this on the Pi after a fresh cluster setup.
#
# Usage:
#   ./create-secrets.sh
#
# Prerequisites:
#   - kubectl configured and cluster running
#   - Namespaces already created (via Flux or manually)
#   - GitHub PAT with read:packages + write:packages scope
# ============================================================

set -euo pipefail

echo "=== Creating Homelab K8s Secrets ==="
echo ""
echo "This script creates all required secrets."
echo "You will be prompted for sensitive values."
echo ""

# --- Prompt for shared credentials ---
read -sp "GitHub PAT (ghcr.io): " GITHUB_PAT && echo
read -sp "Finance Tracker DB password (dev): " FT_DB_PASS_DEV && echo
read -sp "Finance Tracker DB password (prod): " FT_DB_PASS_PROD && echo
read -sp "Bachelor-Demo MariaDB root password: " MARIADB_ROOT_PASS && echo
read -sp "Bachelor-Demo MariaDB matomo password: " MARIADB_MATOMO_PASS && echo
read -sp "Bachelor-Demo Grafana admin password: " GRAFANA_PASS && echo

# ============================================================
# Finance Tracker - Dev
# ============================================================
echo ""
echo "--- financetracker-dev ---"

kubectl create secret docker-registry ghcr-credentials \
  --docker-server=ghcr.io \
  --docker-username=dreyssechris \
  --docker-password="$GITHUB_PAT" \
  -n financetracker-dev --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic postgres-credentials \
  --from-literal=POSTGRES_USER=ft_dbadmin \
  --from-literal=POSTGRES_PASSWORD="$FT_DB_PASS_DEV" \
  --from-literal=POSTGRES_DB=financedb_dev \
  -n financetracker-dev --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic app-secrets \
  --from-literal=ConnectionStrings__DefaultConnection="Host=postgres;Port=5432;Database=financedb_dev;Username=ft_dbadmin;Password=$FT_DB_PASS_DEV" \
  -n financetracker-dev --dry-run=client -o yaml | kubectl apply -f -

echo "  ✓ financetracker-dev secrets created"

# ============================================================
# Finance Tracker - Prod
# ============================================================
echo ""
echo "--- financetracker-prod ---"

kubectl create secret docker-registry ghcr-credentials \
  --docker-server=ghcr.io \
  --docker-username=dreyssechris \
  --docker-password="$GITHUB_PAT" \
  -n financetracker-prod --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic postgres-credentials \
  --from-literal=POSTGRES_USER=ft_dbadmin \
  --from-literal=POSTGRES_PASSWORD="$FT_DB_PASS_PROD" \
  --from-literal=POSTGRES_DB=financedb_prod \
  -n financetracker-prod --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic app-secrets \
  --from-literal=ConnectionStrings__DefaultConnection="Host=postgres;Port=5432;Database=financedb_prod;Username=ft_dbadmin;Password=$FT_DB_PASS_PROD" \
  -n financetracker-prod --dry-run=client -o yaml | kubectl apply -f -

echo "  ✓ financetracker-prod secrets created"

# ============================================================
# Bachelor-Demo
# ============================================================
echo ""
echo "--- bachelor-demo ---"

kubectl create secret generic mariadb-credentials \
  --from-literal=MARIADB_ROOT_PASSWORD="$MARIADB_ROOT_PASS" \
  --from-literal=MYSQL_PASSWORD="$MARIADB_MATOMO_PASS" \
  --from-literal=MYSQL_DATABASE=matomo \
  --from-literal=MYSQL_USER=matomo \
  --from-literal=MATOMO_DATABASE_USERNAME=matomo \
  --from-literal=MATOMO_DATABASE_PASSWORD="$MARIADB_MATOMO_PASS" \
  --from-literal=MATOMO_DATABASE_DBNAME=matomo \
  -n bachelor-demo --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic grafana-credentials \
  --from-literal=GF_SECURITY_ADMIN_PASSWORD="$GRAFANA_PASS" \
  -n bachelor-demo --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret docker-registry ghcr-credentials \
  --docker-server=ghcr.io \
  --docker-username=dreyssechris \
  --docker-password="$GITHUB_PAT" \
  -n bachelor-demo --dry-run=client -o yaml | kubectl apply -f -

echo "  ✓ bachelor-demo secrets created"

# ============================================================
echo ""
echo "=== All secrets created successfully ==="
echo ""
echo "Verify with:"
echo "  kubectl get secrets -n financetracker-dev"
echo "  kubectl get secrets -n financetracker-prod"
echo "  kubectl get secrets -n bachelor-demo"
