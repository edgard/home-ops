#!/usr/bin/env bats

load 'helpers/test_helper.bash'

setup() {
  setup_test_env
  export VERSION_CALLS_FILE="${TEST_TMPDIR}/talos-version-calls"
  : > "${VERSION_CALLS_FILE}"

  write_stub talosctl '
printf "talosctl %s\n" "$*" >> "$STUB_LOG"
if [[ "$1" == "version" ]]; then
  calls=$(wc -l < "$VERSION_CALLS_FILE")
  echo x >> "$VERSION_CALLS_FILE"
  if [[ "$calls" -eq 0 ]]; then
    exit 1
  fi
fi
'
  write_stub kubectl '
printf "kubectl %s\n" "$*" >> "$STUB_LOG"
'
  write_stub sleep '
printf "sleep %s\n" "$*" >> "$STUB_LOG"
'
}

teardown() {
  teardown_test_env
}

@test "talos-bootstrap retries version checks and configures kubectl" {
  run env TALOS_NODE=192.168.1.10 TALOS_CLUSTER_NAME=homelab bash scripts/talos-cluster.sh bootstrap

  [ "$status" -eq 0 ]
  assert_log_contains 'talosctl version --nodes 192.168.1.10'
  assert_log_contains 'sleep 5'
  assert_log_contains 'talosctl bootstrap --nodes 192.168.1.10'
  assert_log_contains 'talosctl health --nodes 192.168.1.10 --wait-timeout 5m'
  assert_log_contains 'talosctl kubeconfig --nodes 192.168.1.10 --context homelab'
  assert_log_contains 'kubectl config use-context admin@homelab'
}

@test "talos-bootstrap fails after exhausting Talos API retries" {
  write_stub talosctl '
printf "talosctl %s\n" "$*" >> "$STUB_LOG"
if [[ "$1" == "version" ]]; then
  exit 1
fi
'

  run env TALOS_NODE=192.168.1.10 TALOS_CLUSTER_NAME=homelab bash scripts/talos-cluster.sh bootstrap

  [ "$status" -ne 0 ]
  run grep -c '^sleep 5$' "$STUB_LOG"
  [ "$output" -eq 30 ]
}
