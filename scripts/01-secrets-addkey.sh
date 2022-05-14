#!/usr/bin/env bash

REPO_ROOT=$(git rev-parse --show-toplevel)

kubectl apply -f "${REPO_ROOT}/.sealed-secrets.key"
kubectl delete pod -n kube-system -l app.kubernetes.io/name=sealed-secrets
