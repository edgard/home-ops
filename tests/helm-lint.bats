#!/usr/bin/env bats

load 'helpers/test_helper.bash'

setup() {
  setup_test_env
  write_stub yq '
printf "yq %s\n" "$*" >> "$STUB_LOG"
if [[ "$2" == ".chart.repo" ]]; then
  cat "$3" | awk "/repo:/{print \$2; exit}"
elif [[ "$2" == ".chart.version" ]]; then
  cat "$3" | awk "/version:/{print \$2; exit}"
elif [[ "$2" == ".chart.name" ]]; then
  cat "$3" | awk "/name:/{print \$2; exit}"
else
  exit 1
fi
'
  write_stub helm '
printf "helm %s\n" "$*" >> "$STUB_LOG"
'
  write_stub md5sum '
printf "abcd1234  -\n"
'

  mkdir -p "${TEST_TMPDIR}/apps/selfhosted/demo"
  cat > "${TEST_TMPDIR}/apps/selfhosted/demo/app.yaml" <<EOF
---
chart:
  repo: oci://ghcr.io/example/app-template
  version: 1.2.3
EOF
  cat > "${TEST_TMPDIR}/apps/selfhosted/demo/values.yaml" <<EOF
---
service:
  main:
    enabled: true
EOF
  mkdir -p "${TEST_TMPDIR}/apps/selfhosted/http-demo"
  cat > "${TEST_TMPDIR}/apps/selfhosted/http-demo/app.yaml" <<EOF
---
chart:
  repo: https://charts.example.com
  name: demo
  version: 2.0.0
EOF
  cat > "${TEST_TMPDIR}/apps/selfhosted/http-demo/values.yaml" <<EOF
---
service:
  main:
    enabled: true
EOF
}

teardown() {
  teardown_test_env
}

@test "validate-helm-apps templates OCI charts with their values file" {
  run bash scripts/validate-helm-apps.sh "${TEST_TMPDIR}/apps/selfhosted/demo/app.yaml"

  [ "$status" -eq 0 ]
  assert_log_contains "helm template test oci://ghcr.io/example/app-template --version 1.2.3 --values ${TEST_TMPDIR}/apps/selfhosted/demo/values.yaml"
}

@test "validate-helm-apps adds and templates HTTP repos with chart names" {
  run bash scripts/validate-helm-apps.sh "${TEST_TMPDIR}/apps/selfhosted/http-demo/app.yaml"

  [ "$status" -eq 0 ]
  assert_log_contains 'helm repo add abcd1234 https://charts.example.com'
  assert_log_contains 'helm repo update abcd1234'
  assert_log_contains "helm template test abcd1234/demo --version 2.0.0 --values ${TEST_TMPDIR}/apps/selfhosted/http-demo/values.yaml"
}
