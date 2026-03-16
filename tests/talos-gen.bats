#!/usr/bin/env bats

load 'helpers/test_helper.bash'

setup() {
  setup_test_env
  write_stub talosctl '
printf "talosctl %s\n" "$*" >> "$STUB_LOG"
output_dir=""
args=("$@")
for ((i = 0; i < ${#args[@]}; i++)); do
  if [[ "${args[$i]}" == "--output-dir" ]]; then
    output_dir="${args[$((i + 1))]}"
  fi
done
mkdir -p "$output_dir"
printf "talos-config" > "$output_dir/talosconfig"
printf "control-plane" > "$output_dir/controlplane.yaml"
'
}

teardown() {
  teardown_test_env
}

@test "talos-gen generates Talos config into HOME" {
  run env TALOS_CLUSTER_NAME=homelab TALOS_NODE=192.168.1.10 TALOS_INSTALL_DISK=/dev/vda bash scripts/talos-cluster.sh gen

  [ "$status" -eq 0 ]
  assert_log_contains 'talosctl gen config homelab https://192.168.1.10:6443 --install-disk /dev/vda --config-patch-control-plane @controlplane-patch.yaml --with-secrets secrets.yaml'
  [ -f "${HOME}/.talos/config" ]
  [ -f "${HOME}/.talos/controlplane.yaml" ]
}
