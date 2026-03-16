#!/usr/bin/env bats

load 'helpers/test_helper.bash'

setup() {
  setup_test_env
  write_stub kubectl '
printf "kubectl %s\n" "$*" >> "$STUB_LOG"
if [[ "$1" == "-n" && "$2" == "argocd" && "$3" == "get" && "$4" == "applications" ]]; then
  printf "application.argoproj.io/app-a\napplication.argoproj.io/app-b\n"
fi
'
}

teardown() {
  teardown_test_env
}

@test "argo-sync filters applications when APP is set" {
  run env APP=plex bash scripts/argocd-app-sync.sh

  [ "$status" -eq 0 ]
  assert_log_contains 'kubectl -n argocd get applications -l app=plex -o name'
  assert_log_contains 'kubectl -n argocd patch --type merge -p {"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}} application.argoproj.io/app-a'
  assert_log_contains 'kubectl -n argocd patch --type merge -p {"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}} application.argoproj.io/app-b'
}

@test "argo-sync refreshes all applications when APP is not set" {
  run bash scripts/argocd-app-sync.sh

  [ "$status" -eq 0 ]
  assert_log_contains 'kubectl -n argocd get applications -o name'
  assert_log_contains 'kubectl -n argocd patch --type merge -p {"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}} application.argoproj.io/app-a'
  assert_log_contains 'kubectl -n argocd patch --type merge -p {"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}} application.argoproj.io/app-b'
}
