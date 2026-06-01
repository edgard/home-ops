#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

mkdir -p "${tmp_dir}/bin"

cat >"${tmp_dir}/talos-upgrade.yaml" <<'YAML'
---
talos:
  installer:
    repository: ghcr.io/siderolabs/installer
    version: v9.9.9
  upgrade:
    rebootMode: default
    timeout: 30m
YAML

cat >"${tmp_dir}/bin/talosctl" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

printf 'talosctl' >>"${COMMAND_LOG:?}"
for arg in "$@"; do
  printf '\t%s' "$arg" >>"$COMMAND_LOG"
done
printf '\n' >>"$COMMAND_LOG"

if [[ "$*" == *" version"* ]]; then
  cat <<'OUT'
Client:
	Tag:         v9.9.9
Server:
	NODE:        192.0.2.10
	Tag:         v9.9.9
OUT
fi
SH

cat >"${tmp_dir}/bin/kubectl" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

printf 'kubectl' >>"${COMMAND_LOG:?}"
for arg in "$@"; do
  printf '\t%s' "$arg" >>"$COMMAND_LOG"
done
printf '\n' >>"$COMMAND_LOG"

if [ "${1:-}" = "get" ] && [ "${2:-}" = "nodes" ]; then
  cat <<'JSON'
{
  "items": [
    {
      "metadata": {"name": "talos-test-node"},
      "status": {
        "addresses": [
          {"type": "InternalIP", "address": "192.0.2.10"}
        ]
      }
    }
  ]
}
JSON
fi
SH

chmod +x "${tmp_dir}/bin/talosctl" "${tmp_dir}/bin/kubectl"

export PATH="${tmp_dir}/bin:${PATH}"
export COMMAND_LOG="${tmp_dir}/commands.log"
export TALOS_NODE="192.0.2.10"
export TALOS_UPGRADE_FILE="${tmp_dir}/talos-upgrade.yaml"

"${repo_root}/scripts/talos-cluster.sh" upgrade

grep -F $'talosctl\t--nodes\t192.0.2.10\tupgrade\t--image\tghcr.io/siderolabs/installer:v9.9.9\t--reboot-mode\tdefault\t--timeout\t30m\t--wait' "$COMMAND_LOG" >/dev/null
grep -F $'kubectl\tuncordon\ttalos-test-node' "$COMMAND_LOG" >/dev/null
grep -F $'talosctl\t--nodes\t192.0.2.10\tversion' "$COMMAND_LOG" >/dev/null
