#!/bin/bash
# ============================================================
# Toggle the bachelor-demo on or off.
#
# Usage:
#   ./bachelor-demo-toggle.sh on     # Start demo
#   ./bachelor-demo-toggle.sh off    # Stop demo
#   ./bachelor-demo-toggle.sh status # Check current state
# ============================================================

set -euo pipefail

ACTION="${1:-status}"

case "$ACTION" in
  on)
    echo "Starting bachelor-demo..."
    flux resume ks bachelor-demo
    flux reconcile ks bachelor-demo --with-source
    echo ""
    echo "Waiting for pods..."
    kubectl get pods -n bachelor-demo -w
    ;;
  off)
    echo "Stopping bachelor-demo..."
    kubectl scale deploy matomo grafana portal -n bachelor-demo --replicas=0
    kubectl scale sts mariadb -n bachelor-demo --replicas=0
    flux suspend ks bachelor-demo
    echo ""
    echo "Bachelor-demo stopped. PVCs remain intact."
    kubectl get pods -n bachelor-demo
    ;;
  status)
    echo "=== Flux Kustomization ==="
    flux get ks bachelor-demo 2>/dev/null || echo "Not found"
    echo ""
    echo "=== Pods ==="
    kubectl get pods -n bachelor-demo 2>/dev/null || echo "No pods"
    echo ""
    echo "=== PVCs ==="
    kubectl get pvc -n bachelor-demo 2>/dev/null || echo "No PVCs"
    ;;
  *)
    echo "Usage: $0 {on|off|status}"
    exit 1
    ;;
esac
