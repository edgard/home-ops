#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="${REPO_ROOT:-$(cd -- "${script_dir}/.." && pwd)}"
manifest="${repo_root}/apps/platform-system/tuppr/manifests/tuppr-kubernetes.kubernetesupgrade.yaml"

[ -f "$manifest" ] || {
  echo "Missing Kubernetes upgrade manifest: $manifest" >&2
  exit 1
}

version="$(yq eval '.spec.kubernetes.version // ""' "$manifest")"
version="${version//\"/}"

if [ -z "$version" ] || [ "$version" = "null" ]; then
  echo "Missing spec.kubernetes.version in $manifest" >&2
  exit 1
fi

printf '%s\n' "$version"
