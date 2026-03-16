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

  echo "==> Waiting for Talos API..."
  for _ in {1..30}; do
    if talosctl version --nodes "$TALOS_NODE" >/dev/null 2>&1; then
      break
    fi
    sleep 5
  done

  talosctl bootstrap --nodes "$TALOS_NODE" || true
  talosctl health --nodes "$TALOS_NODE" --wait-timeout 5m
  talosctl kubeconfig --nodes "$TALOS_NODE" --context "$TALOS_CLUSTER_NAME"
  kubectl config use-context "admin@$TALOS_CLUSTER_NAME"
}

talos_upgrade() {
  cd "$bootstrap_dir"

  : "${TALOS_NODE:?}"

  local controlplane_config="${HOME}/.talos/controlplane.yaml"
  local image

  image=$(yq '.machine.install.image | select(. != null)' "$controlplane_config")
  [[ -z "$image" ]] && echo "No machine.install.image found" && return 1

  talosctl -n "$TALOS_NODE" upgrade --image "$image" --preserve=true --reboot-mode=powercycle
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
