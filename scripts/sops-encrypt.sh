#!/usr/bin/env bash

REPO_ROOT=$(git rev-parse --show-toplevel)
SOPS_PUB_KEY=$(grep "public key" "${REPO_ROOT}/.sops-key" | awk '{print $4}')

sops --age="${SOPS_PUB_KEY}" --encrypt --encrypted-regex '^(data|stringData)$' --in-place "$1"
