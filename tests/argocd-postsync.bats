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

@test "argocd-postsync applies repo credentials, waits, and applies root app" {
  run bash scripts/argocd-bootstrap-postsync.sh

  [ "$status" -eq 0 ]
  assert_log_contains "kubectl apply -f ${REPO_ROOT}/apps/argocd/argocd/manifests/argocd-repo-credentials.externalsecret.yaml"
  assert_log_contains 'kubectl wait --for=condition=Ready --timeout=120s externalsecret/argocd-repo-credentials -n argocd'
  assert_log_contains 'kubectl wait --for=condition=Established --timeout=180s crd/applications.argoproj.io crd/appprojects.argoproj.io crd/applicationsets.argoproj.io'
  assert_log_contains "kubectl apply -f ${REPO_ROOT}/argocd/root.app.yaml"
}
