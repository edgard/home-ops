#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"
wait_medium="${BOOTSTRAP_WAIT_MEDIUM:-120s}"

kubectl apply -f "${repo_root}/apps/platform-system/external-secrets/manifests/external-secrets-store.clustersecretstore.yaml"
kubectl wait --for=condition=Available deployment/bitwarden-sdk-server -n platform-system --timeout="${wait_medium}"
kubectl rollout restart deployment/external-secrets -n platform-system
kubectl rollout status deployment/external-secrets -n platform-system --timeout="${wait_medium}"
