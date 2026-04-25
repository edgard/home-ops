#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"
wait_short="${BOOTSTRAP_WAIT_SHORT:-60s}"
wait_medium="${BOOTSTRAP_WAIT_MEDIUM:-120s}"

: "${BWS_ACCESS_TOKEN:?BWS_ACCESS_TOKEN is required}"

kubectl wait --for=condition=Established crd/issuers.cert-manager.io crd/certificates.cert-manager.io --timeout="${wait_short}"
kubectl wait --for=condition=Available deployment/cert-manager-webhook -n platform-system --timeout="${wait_short}"
kubectl create secret generic bitwarden-credentials --namespace platform-system --from-literal=token="${BWS_ACCESS_TOKEN}" --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f "${repo_root}/apps/platform-system/external-secrets/manifests/external-secrets-sdk-server-issuer.issuer.yaml"
kubectl apply -f "${repo_root}/apps/platform-system/external-secrets/manifests/external-secrets-sdk-server-tls.certificate.yaml"
kubectl wait --for=condition=Ready certificate/external-secrets-sdk-server-tls -n platform-system --timeout="${wait_medium}"
