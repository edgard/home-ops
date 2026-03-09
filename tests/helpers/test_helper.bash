#!/usr/bin/env bash

setup_test_env() {
  export TEST_TMPDIR
  TEST_TMPDIR="$(mktemp -d "${BATS_TEST_TMPDIR}/home-ops.XXXXXX")"
  export STUB_BIN="${TEST_TMPDIR}/bin"
  export STUB_LOG="${TEST_TMPDIR}/commands.log"
  export HOME="${TEST_TMPDIR}/home"

  unset APP
  unset AWS_ACCESS_KEY_ID
  unset AWS_SECRET_ACCESS_KEY
  unset AWS_SESSION_TOKEN
  unset BW_ACCESS_TOKEN
  unset BWS_ACCESS_TOKEN
  unset K8S_VERSION
  unset TALOS_CLUSTER_NAME
  unset TALOS_INSTALL_DISK
  unset TALOS_NODE

  mkdir -p "${STUB_BIN}" "${HOME}"
  : > "${STUB_LOG}"

  export PATH="${STUB_BIN}:$PATH"
}

teardown_test_env() {
  rm -rf "${TEST_TMPDIR}"
}

write_stub() {
  local name="$1"
  local body="$2"

  cat > "${STUB_BIN}/${name}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
${body}
EOF
  chmod +x "${STUB_BIN}/${name}"
}

assert_log_contains() {
  local expected="$1"

  grep -F -- "${expected}" "${STUB_LOG}"
}
