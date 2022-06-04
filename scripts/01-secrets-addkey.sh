#!/usr/bin/env bash

REPO_ROOT=$(git rev-parse --show-toplevel)

kubectl create namespace flux-system --dry-run=client -o yaml | kubectl apply -f -
cat "${REPO_ROOT}/.sops.agekey" | kubectl create secret generic sops-age --namespace=flux-system --from-file=sops.agekey=/dev/stdin
