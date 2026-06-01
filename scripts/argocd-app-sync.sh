#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

APP="${APP:-}"

patch_app() {
  kubectl -n argocd patch "$1" --type merge -p '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}'
}

if [ -n "$APP" ]; then
  patch_app "application/${APP}"
else
  while IFS= read -r app; do
    patch_app "$app"
  done < <(kubectl -n argocd get applications -o name)
fi
