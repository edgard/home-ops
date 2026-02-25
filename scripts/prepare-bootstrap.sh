#!/usr/bin/env bash
set -euo pipefail

k8tz_version="${1:?k8tz version is required}"
warmup_pod="bootstrap-image-warmup-k8tz-${RANDOM}"

for ns in media platform-system; do
  kubectl create namespace "${ns}" --dry-run=client -o yaml | kubectl apply -f -
done

kubectl -n kube-system run -q "${warmup_pod}" --rm --attach --restart=Never --image="quay.io/k8tz/k8tz:${k8tz_version}" -- --help >/dev/null
