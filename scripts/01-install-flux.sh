#!/usr/bin/env bash

REPO_ROOT=$(git rev-parse --show-toplevel)
set -o allexport; source .env; set +o allexport

if [ -z "${GITHUB_USER}" || -z "${GITHUB_REPO}" || -z "$GITHUB_TOKEN" ]; then
    echo "GitHub environment variables not set! Check $REPO_ROOT/.env"
    exit 1
fi

flux check --pre
FLUX_PRE=$?
if [ $FLUX_PRE -ne 0 ]; then
    echo -e "Flux prereqs check failed!"
    exit 1
fi

flux bootstrap github \
    --components-extra=image-reflector-controller,image-automation-controller \
    --owner="${GITHUB_USER}" \
    --repository="${GITHUB_REPO}" \
    --path=cluster \
    --branch=master \
    --read-write-key \
    --personal
