#!/usr/bin/env bash

REPO_ROOT=$(git rev-parse --show-toplevel)

kubeseal --scope cluster-wide --format=yaml --cert="${REPO_ROOT}/.sealed-secrets.pub" < "$1" > "$1-sealed"
mv -f "$1-sealed" "$1"
