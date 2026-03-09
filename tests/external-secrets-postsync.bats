#!/usr/bin/env bats

load 'helpers/test_helper.bash'

setup() {
  setup_test_env
  export REPO_ROOT
  REPO_ROOT="$(cd -- "$(dirname -- "$BATS_TEST_FILENAME")/.." && pwd)"
  write_stub kubectl '
printf "kubectl %s\n" "$*" >> "$STUB_LOG"
'
}

teardown() {
  teardown_test_env
}

@test "external-secrets-postsync reapplies store and restarts controller" {
  run bash scripts/external-secrets-postsync.sh

  [ "$status" -eq 0 ]
  assert_log_contains "kubectl apply -f ${REPO_ROOT}/apps/platform-system/external-secrets/manifests/external-secrets-store.clustersecretstore.yaml"
  assert_log_contains 'kubectl wait --for=condition=Available deployment/bitwarden-sdk-server -n platform-system --timeout=120s'
  assert_log_contains 'kubectl rollout restart deployment/external-secrets -n platform-system'
  assert_log_contains 'kubectl rollout status deployment/external-secrets -n platform-system --timeout=120s'
}
