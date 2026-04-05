#!/usr/bin/env bash
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 <app.yaml>" >&2
  exit 1
fi

cache_root="${HELM_RENDER_CACHE_DIR:-}"

cleanup() {
  [ -z "${temp_cache_root:-}" ] || rm -rf "$temp_cache_root"
}

trap cleanup EXIT

app="$1"
values="${app%app.yaml}values.yaml"

[ -f "$values" ] || exit 0

if [ -z "$cache_root" ]; then
  temp_cache_root="$(mktemp -d)"
  cache_root="$temp_cache_root"
fi

mkdir -p "${cache_root}/charts" "${cache_root}/repos"

repo="$(yq eval '.chart.repo' "$app")"
[ "$repo" = "null" ] && exit 0

version="$(yq eval '.chart.version' "$app")"
name="$(yq eval '.chart.name' "$app")"

if [[ "$repo" == oci://* ]]; then
  chart="$repo"
  chart_name="${repo##*/}"
else
  [ "$name" = "null" ] && exit 0
  repo_name="$(echo "$repo" | md5sum | cut -d" " -f1)"
  repo_ready_file="${cache_root}/repos/${repo_name}.ready"
  if [ ! -f "$repo_ready_file" ]; then
    helm repo add "$repo_name" "$repo" >/dev/null 2>&1 || true
    helm repo update "$repo_name" >/dev/null 2>&1 || true
    : >"$repo_ready_file"
  fi
  chart="$repo_name/$name"
  chart_name="$name"
fi

chart_key="$(printf '%s|%s|%s\n' "$repo" "$chart_name" "$version" | md5sum | cut -d" " -f1)"
chart_dir="${cache_root}/charts/${chart_key}"

if [ ! -d "$chart_dir" ]; then
  pull_dir="$(mktemp -d "${cache_root}/pull.XXXXXX")"
  helm pull "$chart" --version "$version" --untar --untardir "$pull_dir" >/dev/null 2>&1
  mv "${pull_dir}/${chart_name}" "$chart_dir"
  rm -rf "$pull_dir"
fi

helm template test "$chart_dir" --values "$values" \
  --api-versions gateway.networking.k8s.io/v1/HTTPRoute
