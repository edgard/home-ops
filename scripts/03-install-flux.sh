#!/usr/bin/env bash

flux check --pre
FLUX_PRE=$?
if [ ${FLUX_PRE} -ne 0 ]; then
    echo -e "Flux prereqs check failed!"
    exit 1
fi

kubectl create namespace flux-system --dry-run=client -o yaml | kubectl apply -f -
flux bootstrap github \
    --components-extra=image-reflector-controller,image-automation-controller \
    --owner="${GITHUB_USER}" \
    --repository="${GITHUB_REPO}" \
    --path=cluster/base \
    --branch=master \
    --read-write-key \
    --personal
