#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../bootstrap"

TALOS_NODE="${TALOS_NODE:?}"
TALOS_CLUSTER_NAME="${TALOS_CLUSTER_NAME:?}"

echo "==> Waiting for Talos API..."
for _ in {1..30}; do
  if talosctl version --nodes "$TALOS_NODE" >/dev/null 2>&1; then
    break
  fi
  sleep 5
done

talosctl bootstrap --nodes "$TALOS_NODE" || true
talosctl health --nodes "$TALOS_NODE" --wait-timeout 5m
talosctl kubeconfig --nodes "$TALOS_NODE" --context "$TALOS_CLUSTER_NAME"
kubectl config use-context "admin@$TALOS_CLUSTER_NAME"
