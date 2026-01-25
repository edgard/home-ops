#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

APP="${APP:-}"
FILTER=""

[[ -n "$APP" ]] && FILTER="-l app=$APP"

kubectl -n argocd get applications $FILTER -o name | \
  xargs -r -n1 kubectl -n argocd patch --type merge -p '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}' || true
