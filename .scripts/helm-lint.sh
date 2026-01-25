#!/usr/bin/env bash
# Helm chart validation script for pre-commit
set -euo pipefail

# Validate a single config
validate_config() {
  local config="$1"
  local values="${config%config.yaml}values.yaml"

  # Skip if values.yaml doesn't exist
  [ -f "$values" ] || return 0

  # Extract chart info
  local repo
  repo=$(yq eval '.chart.repo' "$config")
  [ "$repo" = "null" ] && return 0

  local version
  version=$(yq eval '.chart.version' "$config")
  local name
  name=$(yq eval '.chart.name' "$config")

  # Handle OCI vs HTTP repos
  local chart
  if [[ "$repo" == oci://* ]]; then
    chart="$repo"
  else
    [ "$name" = "null" ] && return 0
    local repo_name
    repo_name=$(echo "$repo" | md5sum | cut -d" " -f1)
    helm repo add "$repo_name" "$repo" >/dev/null 2>&1 || true
    helm repo update "$repo_name" >/dev/null 2>&1 || true
    chart="$repo_name/$name"
  fi

# Validate chart
  if ! helm template test "$chart" --version "$version" --values "$values" >/dev/null 2>&1; then
    echo "Failed: $(dirname "$config")"
    return 1
  fi
}

# Main: loop through all passed files
if [ $# -eq 0 ]; then
  exit 0
fi

failed=0
for config in "$@"; do
  if ! validate_config "$config"; then
    failed=1
  fi
done

exit $failed
