#!/usr/bin/env bash
# Validate Kubernetes manifests and Helm app renders
set -euo pipefail

script_dir="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="${REPO_ROOT:-$(cd -- "${script_dir}/.." && pwd)}"
crd_catalog='https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'
schema_root="$(mktemp -d)"

trap 'rm -rf "$schema_root"' EXIT

build_local_schemas() {
  local manifest="$1"

  [ -f "$manifest" ] || return 0

  while IFS=$'\t' read -r name group kind version; do
    mkdir -p "${schema_root}/${group}"
    yq -o=json \
      "select(.metadata.name == \"${name}\") | .spec.versions[] | select(.name == \"${version}\") | .schema.openAPIV3Schema" \
      "$manifest" \
      > "${schema_root}/${group}/${kind,,}_${version}.json"
  done < <(
    yq -r '
      select(.kind == "CustomResourceDefinition")
      | . as $crd
      | .spec.versions[]
      | select(.served == true and .schema.openAPIV3Schema != null)
      | [$crd.metadata.name, $crd.spec.group, $crd.spec.names.kind, .name]
      | @tsv
    ' "$manifest"
  )
}

build_schema_catalog() {
  build_local_schemas "${repo_root}/apps/platform-system/gateway-api/manifests/gateway-api-crds.yaml"
  build_local_schemas "${repo_root}/apps/platform-system/homelab-controller/manifests/gatusconfigs.homelab.edgard.org.customresourcedefinition.yaml"
}

validate_appset_inputs() {
  local apps_root="${APPS_ROOT:-${repo_root}/apps}"
  local failed=0
  local tmp_seen_names

  tmp_seen_names="$(mktemp)"

  for app in "${apps_root}"/*/*; do
    [ -d "$app" ] || continue

    local app_file="$app/app.yaml"
    local values_file="$app/values.yaml"

    if [ ! -f "$app_file" ]; then
      echo "Missing metadata file: $app_file"
      failed=1
      continue
    fi

    if [ ! -f "$values_file" ]; then
      echo "Missing values file: $values_file"
      failed=1
    fi

    local category="${app#"${apps_root}/"}"
    category="${category%%/*}"
    local app_name="${app##*/}"
    local generated_name="${category}-${app_name}"

    local existing_path
    existing_path=$(awk -F'|' -v name="$generated_name" '$1 == name { print $2; exit }' "$tmp_seen_names")
    if [ -n "$existing_path" ]; then
      echo "Duplicate generated application name '$generated_name': $app and $existing_path"
      failed=1
    else
      echo "$generated_name|$app" >> "$tmp_seen_names"
    fi

    local chart_repo
    chart_repo=$(yq eval '.chart.repo // ""' "$app_file")
    local chart_version
    chart_version=$(yq eval '.chart.version // ""' "$app_file")
    local chart_name
    chart_name=$(yq eval '.chart.name // ""' "$app_file")
    local sync_wave
    sync_wave=$(yq eval '.sync.wave // ""' "$app_file")

    if [ -z "$chart_repo" ]; then
      echo "Missing chart.repo in $app_file"
      failed=1
    fi

    if [ -z "$chart_version" ]; then
      echo "Missing chart.version in $app_file"
      failed=1
    fi

    if [ -n "$chart_repo" ] && [[ "$chart_repo" != oci://* ]] && [ -z "$chart_name" ]; then
      echo "Missing chart.name for non-OCI chart repo in $app_file"
      failed=1
    fi

    if [ -n "$sync_wave" ] && ! [[ "$sync_wave" =~ ^-?[0-9]+$ ]]; then
      echo "sync.wave must be an integer string in $app_file"
      failed=1
    fi

    if [ "$(yq eval 'has("ignoreDifferences")' "$app_file")" = "true" ]; then
      local ignore_type
      ignore_type=$(yq eval '.ignoreDifferences | type' "$app_file")
      if [ "$ignore_type" != "!!seq" ]; then
        echo "ignoreDifferences must be a list in $app_file"
        failed=1
        continue
      fi

      local ignore_count
      ignore_count=$(yq eval '.ignoreDifferences | length' "$app_file")
      for ((i = 0; i < ignore_count; i++)); do
        local has_group
        has_group=$(yq eval ".ignoreDifferences[$i] | has(\"group\")" "$app_file")
        local has_kind
        has_kind=$(yq eval ".ignoreDifferences[$i] | has(\"kind\")" "$app_file")

        if [ "$has_group" != "true" ] || [ "$has_kind" != "true" ]; then
          echo "ignoreDifferences[$i] must define both group and kind in $app_file"
          failed=1
        fi
      done
    fi
  done

  rm -f "$tmp_seen_names"
  return "$failed"
}

run_kubeconform() {
  local args=(
    -kubernetes-version
    1.35.1
    -schema-location
    "${schema_root}/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json"
    -schema-location
    default
    -schema-location
    "$crd_catalog"
  )

  kubeconform \
    "${args[@]}" \
    "$@"
}

validate_manifests() {
  local paths=()

  if [ -d "${repo_root}/argocd" ]; then
    paths+=("${repo_root}/argocd")
  fi

  if [ -d "${repo_root}/apps" ]; then
    while IFS= read -r -d '' path; do
      paths+=("$path")
    done < <(find "${repo_root}/apps" -mindepth 3 -maxdepth 3 -type d -name manifests -print0 | sort -z)
  fi

  if [ ${#paths[@]} -eq 0 ]; then
    return 0
  fi

  run_kubeconform \
    -skip CustomResourceDefinition,renovate-operator.mogenius.com/v1alpha1/RenovateJob \
    "${paths[@]}"
}

validate_helm_apps() {
  local failed=0

  if [ $# -eq 0 ]; then
    return 0
  fi

  for app in "$@"; do
    local values="${app%app.yaml}values.yaml"

    [ -f "$values" ] || continue

    local repo
    repo=$(yq eval '.chart.repo' "$app")
    [ "$repo" = "null" ] && continue

    local version
    version=$(yq eval '.chart.version' "$app")
    local name
    name=$(yq eval '.chart.name' "$app")

    local chart
    if [[ "$repo" == oci://* ]]; then
      chart="$repo"
    else
      [ "$name" = "null" ] && continue
      local repo_name
      repo_name=$(echo "$repo" | md5sum | cut -d" " -f1)
      helm repo add "$repo_name" "$repo" >/dev/null 2>&1 || true
      helm repo update "$repo_name" >/dev/null 2>&1 || true
      chart="$repo_name/$name"
    fi

    local rendered
    rendered=$(mktemp)

    if ! helm template test "$chart" --version "$version" --values "$values" \
      --api-versions gateway.networking.k8s.io/v1/HTTPRoute >"$rendered"; then
      rm -f "$rendered"
      echo "Failed: $(dirname "$app")"
      failed=1
      continue
    fi

    if ! run_kubeconform -skip CustomResourceDefinition <"$rendered"; then
      rm -f "$rendered"
      echo "Failed: $(dirname "$app")"
      failed=1
      continue
    fi

    if ! pluto detect - --target-versions k8s=v1.35.1 -o wide <"$rendered"; then
      rm -f "$rendered"
      echo "Failed: $(dirname "$app")"
      failed=1
      continue
    fi

    rm -f "$rendered"
  done

  return "$failed"
}

main() {
  local command="${1:-}"

  build_schema_catalog

  case "$command" in
    appset-inputs)
      shift
      validate_appset_inputs "$@"
      ;;
    manifests)
      shift
      validate_manifests "$@"
      ;;
    helm-apps)
      shift
      validate_helm_apps "$@"
      ;;
    *)
      echo "Usage: $0 <appset-inputs|manifests|helm-apps> [args...]" >&2
      exit 1
      ;;
  esac
}

main "$@"
