#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../bootstrap"

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

talosctl gen config "${TALOS_CLUSTER_NAME:?}" "https://${TALOS_NODE:?}:6443" \
  --install-disk "${TALOS_INSTALL_DISK:?}" \
  --config-patch-control-plane "@controlplane-patch.yaml" \
  --with-secrets "secrets.yaml" \
  --output-dir "$tmp_dir" \
  --force

mkdir -p "$HOME/.talos"
mv -f "$tmp_dir/talosconfig" "$HOME/.talos/config"
mv -f "$tmp_dir/controlplane.yaml" "$HOME/.talos/controlplane.yaml"
