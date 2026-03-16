#!/usr/bin/env bats

load 'helpers/test_helper.bash'

setup() {
  setup_test_env
  write_stub kubectl '
printf "kubectl %s\n" "$*" >> "$STUB_LOG"
'
}

teardown() {
  teardown_test_env
}

@test "prepare-bootstrap creates namespaces and warms up k8tz image" {
  run bash scripts/bootstrap-prepare.sh 0.17.0

  [ "$status" -eq 0 ]
  assert_log_contains 'kubectl create namespace media --dry-run=client -o yaml'
  assert_log_contains 'kubectl create namespace platform-system --dry-run=client -o yaml'
  assert_log_contains 'kubectl apply -f -'
  grep -E 'kubectl -n kube-system run -q bootstrap-image-warmup-k8tz-[0-9]+ --rm --attach --restart=Never --image=quay.io/k8tz/k8tz:0.17.0 -- --help' "$STUB_LOG"
}
