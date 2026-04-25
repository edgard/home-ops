#!/usr/bin/env bash
set -euo pipefail

k8tz_version="${1:?k8tz version is required}"
warmup_timeout="${BOOTSTRAP_IMAGE_WARMUP_TIMEOUT:-120s}"
warmup_pod="bootstrap-image-warmup-k8tz-${RANDOM}"

cleanup_warmup() {
  kubectl -n kube-system delete pod "${warmup_pod}" --ignore-not-found --wait=false >/dev/null 2>&1 || true
}

trap cleanup_warmup EXIT
trap 'cleanup_warmup; exit 130' INT
trap 'cleanup_warmup; exit 143' TERM

kubectl create namespace media --dry-run=client -o yaml | kubectl apply -f -
kubectl -n kube-system run -q "${warmup_pod}" --restart=Never --image="quay.io/k8tz/k8tz:${k8tz_version}" -- --help >/dev/null
kubectl -n kube-system wait --for=jsonpath='{.status.phase}'=Succeeded "pod/${warmup_pod}" --timeout="${warmup_timeout}" >/dev/null
