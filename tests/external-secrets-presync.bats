#!/usr/bin/env bats

load 'helpers/test_helper.bash'

setup() {
  setup_test_env
  write_stub kubectl '
printf "kubectl %s\n" "$*" >> "$STUB_LOG"
if [[ "$1" == "apply" && "$2" == "-f" && "$3" == "-" ]]; then
  cat >> "$STUB_LOG"
fi
'
}

teardown() {
  teardown_test_env
}

@test "external-secrets-presync requires a Bitwarden token" {
  run bash scripts/external-secrets-presync.sh

  [ "$status" -ne 0 ]
  [[ "$output" == *'BWS_ACCESS_TOKEN is required'* ]]
}

@test "external-secrets-presync creates credentials secret and waits for certificate" {
  run env BWS_ACCESS_TOKEN=token-123 bash scripts/external-secrets-presync.sh

  [ "$status" -eq 0 ]
  assert_log_contains 'kubectl wait --for=condition=Established crd/issuers.cert-manager.io crd/certificates.cert-manager.io --timeout=60s'
  assert_log_contains 'name: bitwarden-credentials'
  assert_log_contains 'token: token-123'
  assert_log_contains 'kubectl apply -f /Users/edgard/Documents/Projects/Personal/home-ops/apps/platform-system/external-secrets/manifests/external-secrets-sdk-server-issuer.issuer.yaml'
  assert_log_contains 'kubectl apply -f /Users/edgard/Documents/Projects/Personal/home-ops/apps/platform-system/external-secrets/manifests/external-secrets-sdk-server-tls.certificate.yaml'
  assert_log_contains 'kubectl wait --for=condition=Ready certificate/external-secrets-sdk-server-tls -n platform-system --timeout=120s'
}
