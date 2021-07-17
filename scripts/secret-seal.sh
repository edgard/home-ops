#!/usr/bin/env bash

REPO_ROOT=$(git rev-parse --show-toplevel)

kubectl get secret $1 -o yaml | kubeseal --format yaml --cert ${REPO_ROOT}/secrets/.pub-sealed-secrets.pem | kubectl apply -f -
