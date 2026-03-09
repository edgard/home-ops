#!/usr/bin/env bats

load 'helpers/test_helper.bash'

setup() {
  setup_test_env
}

teardown() {
  teardown_test_env
}

@test "validate-appset-inputs accepts a valid apps tree" {
  mkdir -p "${TEST_TMPDIR}/fixtures/apps/selfhosted/demo"
  cat > "${TEST_TMPDIR}/fixtures/apps/selfhosted/demo/app.yaml" <<EOF
---
chart:
  repo: oci://ghcr.io/example/chart
  version: 1.0.0
sync:
  wave: "-1"
ignoreDifferences:
  - group: apps
    kind: Deployment
EOF
  cat > "${TEST_TMPDIR}/fixtures/apps/selfhosted/demo/values.yaml" <<EOF
---
service:
  main:
    enabled: true
EOF

  run env APPS_ROOT="${TEST_TMPDIR}/fixtures/apps" bash scripts/validate-appset-inputs.sh

  [ "$status" -eq 0 ]
}

@test "validate-appset-inputs reports missing values and malformed metadata" {
  mkdir -p "${TEST_TMPDIR}/fixtures/apps/selfhosted/demo"
  cat > "${TEST_TMPDIR}/fixtures/apps/selfhosted/demo/app.yaml" <<EOF
---
chart:
  repo: https://charts.example.com
  version: ""
sync:
  wave: invalid
ignoreDifferences:
  group: apps
EOF

  run env APPS_ROOT="${TEST_TMPDIR}/fixtures/apps" bash scripts/validate-appset-inputs.sh

  [ "$status" -ne 0 ]
  [[ "$output" == *"Missing values file:"* ]]
  [[ "$output" == *"Missing chart.version"* ]]
  [[ "$output" == *"Missing chart.name for non-OCI chart repo"* ]]
  [[ "$output" == *"sync.wave must be an integer string"* ]]
  [[ "$output" == *"ignoreDifferences must be a list"* ]]
}
