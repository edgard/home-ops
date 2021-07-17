#!/usr/bin/env bash

REPO_ROOT=$(git rev-parse --show-toplevel)

kubeseal --fetch-cert --controller-name=sealed-secrets --controller-namespace=infra-system > "${REPO_ROOT}/secrets/.pub-sealed-secrets.pem"
kubectl get secret -n infra-system -l sealedsecrets.bitnami.com/sealed-secrets-key -o yaml > "${REPO_ROOT}/secrets/.sealed-secrets-master-key.yaml"
