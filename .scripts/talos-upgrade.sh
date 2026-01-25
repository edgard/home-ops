#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../bootstrap"

TALOS_NODE="${TALOS_NODE:?}"
CONTROLPLANE_CONFIG="${HOME}/.talos/controlplane.yaml"

IMAGE=$(yq '.machine.install.image | select(. != null)' "$CONTROLPLANE_CONFIG")
[[ -z "$IMAGE" ]] && echo "No machine.install.image found" && exit 1

talosctl -n "$TALOS_NODE" upgrade --image "$IMAGE" --preserve=true --reboot-mode=powercycle
