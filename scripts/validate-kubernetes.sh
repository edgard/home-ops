#!/usr/bin/env bash
# Validate Kubernetes manifests and Helm app renders
set -euo pipefail

script_dir="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="${REPO_ROOT:-$(cd -- "${script_dir}/.." && pwd)}"
crd_catalog='https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'
schema_root=""
render_cache_root=""
schema_catalog_built=0

cleanup() {
  [ -z "$schema_root" ] || rm -rf "$schema_root"
  [ -z "$render_cache_root" ] || rm -rf "$render_cache_root"
}

trap cleanup EXIT

ensure_schema_root() {
  [ -n "$schema_root" ] || schema_root="$(mktemp -d)"
}

ensure_render_cache_root() {
  [ -n "$render_cache_root" ] || render_cache_root="$(mktemp -d)"
}

yaml_quote() {
  local value="$1"

  value="${value//\'/\'\'}"
  printf "'%s'" "$value"
}

build_local_schemas() {
  local manifest="$1"

  [ -f "$manifest" ] || return 0
  ensure_schema_root

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
  if [ "$schema_catalog_built" -eq 1 ]; then
    return 0
  fi

  ensure_schema_root
  build_local_schemas "${repo_root}/apps/platform-system/gateway-api/manifests/gateway-api-crds.yaml"
  build_local_schemas "${repo_root}/apps/platform-system/homelab-controller/manifests/gatusconfigs.homelab.edgard.org.customresourcedefinition.yaml"
  schema_catalog_built=1
}

get_kubernetes_target_version() {
  local manifest="${repo_root}/apps/platform-system/tuppr/manifests/tuppr-kubernetes.kubernetesupgrade.yaml"
  local version

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
}

raw_manifest_paths() {
  if [ -d "${repo_root}/argocd" ]; then
    printf '%s\0' "${repo_root}/argocd"
  fi

  if [ -d "${repo_root}/apps" ]; then
    find "${repo_root}/apps" -mindepth 3 -maxdepth 3 -type d -name manifests -print0 | sort -z
  fi
}

rendered_output_relative_path() {
  local app="$1"
  local relative_path=""

  if [[ "$app" == "${repo_root}/apps/"*"/app.yaml" ]]; then
    relative_path="${app#"${repo_root}/apps/"}"
    printf '%s\n' "${relative_path%/app.yaml}.yaml"
    return 0
  fi

  if [[ "$app" == "${repo_root}/"*"/app.yaml" ]]; then
    relative_path="${app#"${repo_root}/"}"
    printf '%s\n' "${relative_path%/app.yaml}.yaml"
    return 0
  fi

  relative_path="${app%/app.yaml}"
  relative_path="${relative_path#/}"
  relative_path="${relative_path//\//__}"
  printf 'external/%s.yaml\n' "$relative_path"
}

run_kubeconform() {
  local kubernetes_version="$1"
  shift

  build_schema_catalog

  local args=(
    -kubernetes-version
    "${kubernetes_version#v}"
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

write_metadata_inventory() {
  local apps_root="${repo_root}/apps"

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
      local ignore_differences_count has_group has_kind
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

validate_metadata() {
  local workdir inventory status

  workdir="$(mktemp -d)"
  inventory="${workdir}/app-metadata.yaml"
  write_metadata_inventory >"$inventory"

  if conftest test --no-color --policy "${repo_root}/policy/metadata" "$inventory"; then
    status=0
  else
    status=$?
  fi

  rm -rf "$workdir"
  return "$status"
}

render_helm_app() {
  local app="$1"
  local values="${app%app.yaml}values.yaml"
  local repo version name chart chart_name chart_key chart_dir

  [ -f "$values" ] || return 0

  ensure_render_cache_root
  mkdir -p "${render_cache_root}/charts" "${render_cache_root}/repos"

  repo="$(yq eval '.chart.repo' "$app")"
  [ "$repo" = "null" ] && return 0

  version="$(yq eval '.chart.version' "$app")"
  name="$(yq eval '.chart.name' "$app")"

  if [[ "$repo" == oci://* ]]; then
    chart="$repo"
    chart_name="${repo##*/}"
  else
    local repo_name repo_ready_file

    [ "$name" = "null" ] && return 0
    repo_name="$(echo "$repo" | md5sum | cut -d" " -f1)"
    repo_ready_file="${render_cache_root}/repos/${repo_name}.ready"
    if [ ! -f "$repo_ready_file" ]; then
      helm repo add "$repo_name" "$repo" >/dev/null 2>&1 || true
      helm repo update "$repo_name" >/dev/null 2>&1 || true
      : >"$repo_ready_file"
    fi
    chart="$repo_name/$name"
    chart_name="$name"
  fi

  chart_key="$(printf '%s|%s|%s\n' "$repo" "$chart_name" "$version" | md5sum | cut -d" " -f1)"
  chart_dir="${render_cache_root}/charts/${chart_key}"

  if [ ! -d "$chart_dir" ]; then
    local pull_dir
    pull_dir="$(mktemp -d "${render_cache_root}/pull.XXXXXX")"
    helm pull "$chart" --version "$version" --untar --untardir "$pull_dir" >/dev/null 2>&1
    mv "${pull_dir}/${chart_name}" "$chart_dir"
    rm -rf "$pull_dir"
  fi

  helm template test "$chart_dir" --values "$values" \
    --api-versions gateway.networking.k8s.io/v1/HTTPRoute
}

validate_policies() {
  local paths=()
  local policy_dir="${repo_root}/policy/kubernetes"

  while IFS= read -r -d '' path; do
    paths+=("$path")
  done < <(raw_manifest_paths)

  if [ ${#paths[@]} -eq 0 ]; then
    return 0
  fi

  conftest test --no-color --policy "$policy_dir" "${paths[@]}"
}

validate_manifests() {
  local paths=()
  local kubernetes_version

  while IFS= read -r -d '' path; do
    paths+=("$path")
  done < <(raw_manifest_paths)

  if [ ${#paths[@]} -eq 0 ]; then
    return 0
  fi

  kubernetes_version="$(get_kubernetes_target_version)"

  run_kubeconform "$kubernetes_version" \
    -skip CustomResourceDefinition,renovate-operator.mogenius.com/v1alpha1/RenovateJob \
    "${paths[@]}"
}

validate_rendered_apps() {
  local modes=()
  local failed=0
  local kubernetes_version
  local rendered_root
  local rendered_paths=()

  while [ $# -gt 0 ]; do
    case "$1" in
      --)
        shift
        break
        ;;
      *)
        modes+=("$1")
        shift
        ;;
    esac
  done

  if [ ${#modes[@]} -eq 0 ]; then
    echo "At least one rendered validation mode is required" >&2
    return 1
  fi

  if [ $# -eq 0 ]; then
    return 0
  fi

  kubernetes_version="$(get_kubernetes_target_version)"
  ensure_render_cache_root
  rendered_root="$(mktemp -d "${render_cache_root}/rendered.XXXXXX")"

  for app in "$@"; do
    local values="${app%app.yaml}values.yaml"
    local rendered
    local relative_path

    [ -f "$values" ] || continue

    relative_path="$(rendered_output_relative_path "$app")"

    rendered="${rendered_root}/${relative_path}"
    mkdir -p "$(dirname "$rendered")"

    if ! render_helm_app "$app" >"$rendered"; then
      rm -f "$rendered"
      echo "Failed: $(dirname "$app")"
      failed=1
      continue
    fi
    rendered_paths+=("$rendered")
  done

  if [ ${#rendered_paths[@]} -eq 0 ]; then
    return "$failed"
  fi

  for mode in "${modes[@]}"; do
    case "$mode" in
      schema)
        if ! run_kubeconform "$kubernetes_version" -skip CustomResourceDefinition "${rendered_paths[@]}"; then
          echo "Rendered schema validation failed in ${rendered_root}"
          failed=1
        fi
        ;;
      deprecations)
        if ! pluto detect-files -d "$rendered_root" --target-versions "k8s=${kubernetes_version}" -o wide; then
          echo "Rendered deprecation validation failed in ${rendered_root}"
          failed=1
        fi
        ;;
      policy)
        if ! conftest test --no-color --parser yaml --policy "${repo_root}/policy/kubernetes" "${rendered_paths[@]}"; then
          echo "Rendered policy validation failed in ${rendered_root}"
          failed=1
        fi
        ;;
      *)
        echo "Unknown rendered validation mode: $mode" >&2
        return 1
        ;;
    esac
  done

  return "$failed"
}

validate_deprecations() {
  local kubernetes_version

  kubernetes_version="$(get_kubernetes_target_version)"
  pluto detect-files -d "${repo_root}" --target-versions "k8s=${kubernetes_version}" -o wide
}

validate_helm_apps() {
  validate_rendered_apps policy schema deprecations -- "$@"
}

main() {
  local command="${1:-}"

  case "$command" in
    metadata|appset-inputs)
      shift
      validate_metadata "$@"
      ;;
    manifests)
      shift
      validate_manifests "$@"
      ;;
    policies)
      shift
      validate_policies "$@"
      ;;
    rendered-manifests)
      shift
      validate_rendered_apps schema -- "$@"
      ;;
    rendered-policies)
      shift
      validate_rendered_apps policy -- "$@"
      ;;
    deprecations)
      shift
      validate_deprecations "$@"
      ;;
    rendered-deprecations)
      shift
      validate_rendered_apps deprecations -- "$@"
      ;;
    helm-apps)
      shift
      validate_helm_apps "$@"
      ;;
    *)
      echo "Usage: $0 <metadata|appset-inputs|policies|manifests|rendered-policies|rendered-manifests|deprecations|rendered-deprecations|helm-apps> [args...]" >&2
      exit 1
      ;;
  esac
}

main "$@"
