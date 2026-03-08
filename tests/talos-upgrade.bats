#!/usr/bin/env bats

load 'helpers/test_helper.bash'

setup() {
  setup_test_env
  mkdir -p "${HOME}/.talos"
}

teardown() {
  teardown_test_env
}

@test "talos-upgrade fails when machine.install.image is missing" {
  cat > "${HOME}/.talos/controlplane.yaml" <<EOF
machine: {}
EOF

  write_stub yq '
printf "yq %s\n" "$*" >> "$STUB_LOG"
'
  write_stub talosctl '
printf "talosctl %s\n" "$*" >> "$STUB_LOG"
'

  run env TALOS_NODE=192.168.1.10 bash scripts/talos-upgrade.sh

  [ "$status" -ne 0 ]
  [[ "$output" == *'No machine.install.image found'* ]]
}

@test "talos-upgrade uses the image from the control plane config" {
  cat > "${HOME}/.talos/controlplane.yaml" <<EOF
machine:
  install:
    image: factory.talos.dev/installer:v1.10.0
EOF

  write_stub yq '
printf "yq %s\n" "$*" >> "$STUB_LOG"
printf "factory.talos.dev/installer:v1.10.0\n"
'
  write_stub talosctl '
printf "talosctl %s\n" "$*" >> "$STUB_LOG"
'

  run env TALOS_NODE=192.168.1.10 bash scripts/talos-upgrade.sh

  [ "$status" -eq 0 ]
  assert_log_contains 'talosctl -n 192.168.1.10 upgrade --image factory.talos.dev/installer:v1.10.0 --preserve=true --reboot-mode=powercycle'
}
