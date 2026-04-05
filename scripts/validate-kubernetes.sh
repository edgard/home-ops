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
  "${script_dir}/kubernetes-target-version.sh"
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

validate_metadata() {
  "${script_dir}/validate-app-metadata.sh"
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

    if ! HELM_RENDER_CACHE_DIR="$render_cache_root" "${script_dir}/render-helm-app.sh" "$app" >"$rendered"; then
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
