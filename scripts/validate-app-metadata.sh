#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="${REPO_ROOT:-$(cd -- "${script_dir}/.." && pwd)}"
apps_root="${APPS_ROOT:-${repo_root}/apps}"
workdir="$(mktemp -d)"
inventory="${workdir}/app-metadata.yaml"

cleanup() {
  rm -rf "$workdir"
}

trap cleanup EXIT

yaml_quote() {
  local value="$1"

  value="${value//\'/\'\'}"
  printf "'%s'" "$value"
}

write_inventory() {
  printf -- "---\napps:\n"

  for app in "${apps_root}"/*/*; do
    [ -d "$app" ] || continue

    local app_file="$app/app.yaml"
    local values_file="$app/values.yaml"
    local category="${app#"${apps_root}/"}"
    local app_name chart_repo chart_version chart_name sync_wave
    local has_app_file has_values_file has_nonempty_values_file has_ignore_differences ignore_differences_type

    category="${category%%/*}"
    app_name="${app##*/}"
    has_app_file=false
    has_values_file=false
    has_nonempty_values_file=false
    chart_repo=""
    chart_version=""
    chart_name=""
    sync_wave=""
    has_ignore_differences=false
    ignore_differences_type=""

    if [ -f "$app_file" ]; then
      has_app_file=true
      chart_repo="$(yq eval '.chart.repo // ""' "$app_file")"
      chart_version="$(yq eval '.chart.version // ""' "$app_file")"
      chart_name="$(yq eval '.chart.name // ""' "$app_file")"
      sync_wave="$(yq eval '.sync.wave // ""' "$app_file")"
      has_ignore_differences="$(yq eval 'has("ignoreDifferences")' "$app_file")"
      if [ "$has_ignore_differences" = "true" ]; then
        ignore_differences_type="$(yq eval '.ignoreDifferences | type' "$app_file")"
      fi
    fi

    if [ -f "$values_file" ]; then
      has_values_file=true
      if [ -s "$values_file" ]; then
        has_nonempty_values_file=true
      fi
    fi

    printf '  - path: %s\n' "$(yaml_quote "$app")"
    printf '    category: %s\n' "$(yaml_quote "$category")"
    printf '    app_name: %s\n' "$(yaml_quote "$app_name")"
    printf '    generated_name: %s\n' "$(yaml_quote "${category}-${app_name}")"
    printf '    app_file: %s\n' "$(yaml_quote "$app_file")"
    printf '    values_file: %s\n' "$(yaml_quote "$values_file")"
    printf '    has_app_file: %s\n' "$has_app_file"
    printf '    has_values_file: %s\n' "$has_values_file"
    printf '    has_nonempty_values_file: %s\n' "$has_nonempty_values_file"
    printf '    chart_repo: %s\n' "$(yaml_quote "$chart_repo")"
    printf '    chart_version: %s\n' "$(yaml_quote "$chart_version")"
    printf '    chart_name: %s\n' "$(yaml_quote "$chart_name")"
    printf '    sync_wave: %s\n' "$(yaml_quote "$sync_wave")"
    printf '    has_ignore_differences: %s\n' "$has_ignore_differences"
    printf '    ignore_differences_type: %s\n' "$(yaml_quote "$ignore_differences_type")"
    printf '    ignore_differences:\n'

    if [ "$has_app_file" = "true" ] && [ "$ignore_differences_type" = "!!seq" ]; then
      ignore_differences_count="$(yq eval '.ignoreDifferences | length' "$app_file")"
      for ((i = 0; i < ignore_differences_count; i++)); do
        has_group="$(yq eval ".ignoreDifferences[$i] | has(\"group\")" "$app_file")"
        has_kind="$(yq eval ".ignoreDifferences[$i] | has(\"kind\")" "$app_file")"
        printf '      - index: %d\n' "$i"
        printf '        has_group: %s\n' "$has_group"
        printf '        has_kind: %s\n' "$has_kind"
      done
    fi
  done
}

failed=0

write_inventory >"$inventory"

if ! conftest test --no-color --policy "${repo_root}/policy/metadata" "$inventory"; then
  failed=1
fi

if ! "${script_dir}/validate-generated-app-names.sh"; then
  failed=1
fi

exit "$failed"
