#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"
bootstrap_dir="${repo_root}/bootstrap"

talos_gen() {
  cd "$bootstrap_dir"

  local tmp_dir
  tmp_dir="$(mktemp -d)"

  talosctl gen config "${TALOS_CLUSTER_NAME:?}" "https://${TALOS_NODE:?}:6443" \
    --install-disk "${TALOS_INSTALL_DISK:?}" \
    --config-patch-control-plane "@controlplane-patch.yaml" \
    --with-secrets "secrets.yaml" \
    --output-dir "$tmp_dir" \
    --force

  mkdir -p "$HOME/.talos"
  mv -f "$tmp_dir/talosconfig" "$HOME/.talos/config"
  mv -f "$tmp_dir/controlplane.yaml" "$HOME/.talos/controlplane.yaml"
  rm -rf "$tmp_dir"
}

talos_bootstrap() {
  cd "$bootstrap_dir"

  : "${TALOS_NODE:?}"
  : "${TALOS_CLUSTER_NAME:?}"

  local api_ready=0

  echo "==> Waiting for Talos API..."
  for _ in {1..30}; do
    if talosctl version --nodes "$TALOS_NODE" >/dev/null 2>&1; then
      api_ready=1
      break
    fi
    sleep 5
  done

  if [ "$api_ready" -ne 1 ]; then
    echo "Talos API did not become ready for ${TALOS_NODE}" >&2
    return 1
  fi

  talosctl bootstrap --nodes "$TALOS_NODE" || true
  talosctl health --nodes "$TALOS_NODE" --wait-timeout 5m
  talosctl kubeconfig --nodes "$TALOS_NODE" --context "$TALOS_CLUSTER_NAME"
  kubectl config use-context "admin@$TALOS_CLUSTER_NAME"
}

talos_upgrade() {
  : "${TALOS_NODE:?}"

  local upgrade_file="${TALOS_UPGRADE_FILE:-${bootstrap_dir}/talos-upgrade.yaml}"
  local repository version image reboot_mode timeout k8s_node server_version

  [ -f "$upgrade_file" ] || {
    echo "Missing Talos upgrade file: ${upgrade_file}" >&2
    return 1
  }

  repository="$(yq -r '.talos.installer.repository // ""' "$upgrade_file")"
  version="$(yq -r '.talos.installer.version // ""' "$upgrade_file")"
  reboot_mode="$(yq -r '.talos.upgrade.rebootMode // "default"' "$upgrade_file")"
  timeout="$(yq -r '.talos.upgrade.timeout // "30m"' "$upgrade_file")"

  if [ -z "$repository" ] || [ -z "$version" ]; then
    echo "Missing talos.installer.repository or talos.installer.version in ${upgrade_file}" >&2
    return 1
  fi

  image="${repository}:${version}"

  talosctl --nodes "$TALOS_NODE" upgrade \
    --image "$image" \
    --reboot-mode "$reboot_mode" \
    --timeout "$timeout" \
    --wait

  k8s_node="$(kubectl get nodes -o json | jq -r --arg node "$TALOS_NODE" '
    .items[]
    | select(
        .metadata.name == $node
        or any(.status.addresses[]?; .type == "InternalIP" and .address == $node)
      )
    | .metadata.name
  ' | head -n1)"

  if [ -n "$k8s_node" ]; then
    kubectl uncordon "$k8s_node" || true
  fi

  server_version="$(talosctl --nodes "$TALOS_NODE" version | awk '
    /^Server:/ { in_server = 1; next }
    in_server && /^[[:space:]]*Tag:/ { print $2; exit }
  ')"

  if [ "$server_version" != "$version" ]; then
    echo "Talos server version mismatch: current=${server_version:-unknown}, target=${version}" >&2
    return 1
  fi
}

main() {
  case "${1:-}" in
    gen)
      shift
      talos_gen "$@"
      ;;
    bootstrap)
      shift
      talos_bootstrap "$@"
      ;;
    upgrade)
      shift
      talos_upgrade "$@"
      ;;
    *)
      echo "Usage: $0 <gen|bootstrap|upgrade>" >&2
      exit 1
      ;;
  esac
}

main "$@"
