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

@test "argocd-postsync applies repo credentials, waits, and applies root app" {
  run bash scripts/argocd-postsync.sh

  [ "$status" -eq 0 ]
  assert_log_contains 'kubectl apply -f /Users/edgard/Documents/Projects/Personal/home-ops/apps/argocd/argocd/manifests/argocd-repo-credentials.externalsecret.yaml'
  assert_log_contains 'kubectl wait --for=condition=Ready --timeout=120s externalsecret/argocd-repo-credentials -n argocd'
  assert_log_contains 'kubectl wait --for=condition=Established --timeout=180s crd/applications.argoproj.io crd/appprojects.argoproj.io crd/applicationsets.argoproj.io'
  assert_log_contains 'kubectl apply -f /Users/edgard/Documents/Projects/Personal/home-ops/argocd/root.app.yaml'
}
