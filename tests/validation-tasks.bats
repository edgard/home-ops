#!/usr/bin/env bats

load 'helpers/test_helper.bash'

setup() {
  setup_test_env

  cp "${BATS_TEST_DIRNAME}/../Taskfile.yaml" "${TEST_TMPDIR}/Taskfile.yaml"
  cp -R "${BATS_TEST_DIRNAME}/../scripts" "${TEST_TMPDIR}/scripts"
  mkdir -p "${TEST_TMPDIR}/tests"
  cp -R "${BATS_TEST_DIRNAME}/../policy" "${TEST_TMPDIR}/policy" 2>/dev/null || true
  mkdir -p "${TEST_TMPDIR}/terraform"

  mkdir -p "${TEST_TMPDIR}/apps/selfhosted/demo"
  cat > "${TEST_TMPDIR}/apps/selfhosted/demo/app.yaml" <<EOF
---
chart:
  repo: oci://ghcr.io/example/app-template
  version: 1.2.3
sync:
  wave: "0"
EOF
  cat > "${TEST_TMPDIR}/apps/selfhosted/demo/values.yaml" <<EOF
---
service:
  main:
    enabled: true
EOF

  mkdir -p "${TEST_TMPDIR}/apps/selfhosted/bad-demo"
  cat > "${TEST_TMPDIR}/apps/selfhosted/bad-demo/app.yaml" <<EOF
---
chart:
  repo: https://charts.example.com
  version: ""
sync:
  wave: invalid
ignoreDifferences:
  group: apps
EOF

  mkdir -p "${TEST_TMPDIR}/apps/platform-system/tuppr/manifests"
  cat > "${TEST_TMPDIR}/apps/platform-system/tuppr/app.yaml" <<EOF
---
chart:
  repo: oci://ghcr.io/home-operations/charts/tuppr
  version: 0.1.3
sync:
  wave: "-3"
EOF
  cat > "${TEST_TMPDIR}/apps/platform-system/tuppr/values.yaml" <<EOF
---
service:
  main:
    enabled: true
EOF
  cat > "${TEST_TMPDIR}/apps/platform-system/tuppr/manifests/tuppr-kubernetes.kubernetesupgrade.yaml" <<EOF
---
apiVersion: tuppr.home-operations.com/v1alpha1
kind: KubernetesUpgrade
metadata:
  name: kubernetes
spec:
  kubernetes:
    version: v9.9.9
EOF

  mkdir -p "${TEST_TMPDIR}/argocd/projects"
  cat > "${TEST_TMPDIR}/argocd/projects/demo.appproject.yaml" <<EOF
---
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: demo
  namespace: argocd
spec: {}
EOF

  write_stub helm '
printf "helm %s\n" "$*" >> "$STUB_LOG"
if [[ "$1" == "pull" ]]; then
  untardir=""
  source=""
  expect_untardir=""
  expect_version=""
  for arg in "$@"; do
    if [[ -n "$expect_untardir" ]]; then
      untardir="$arg"
      expect_untardir=""
      continue
    fi
    if [[ -n "$expect_version" ]]; then
      expect_version=""
      continue
    fi
    case "$arg" in
      pull)
        ;;
      --untardir)
        expect_untardir=1
        ;;
      --version)
        expect_version=1
        ;;
      --untar)
        ;;
      *)
        if [[ -z "$source" ]]; then
          source="$arg"
        fi
        ;;
    esac
  done
  chart_name="${source##*/}"
  mkdir -p "${untardir}/${chart_name}"
fi
'
  write_stub kubeconform '
printf "kubeconform %s\n" "$*" >> "$STUB_LOG"
: 
'
  write_stub pluto '
printf "pluto %s\n" "$*" >> "$STUB_LOG"
: 
'
  write_stub md5sum '
printf "abcd1234  -\n"
'
  write_stub conftest '
printf "conftest %s\n" "$*" >> "$STUB_LOG"
'
  write_stub shellcheck '
printf "shellcheck %s\n" "$*" >> "$STUB_LOG"
'
  write_stub yamllint '
printf "yamllint %s\n" "$*" >> "$STUB_LOG"
'
  write_stub bats '
printf "bats %s\n" "$*" >> "$STUB_LOG"
'
  write_stub prettier '
printf "prettier %s\n" "$*" >> "$STUB_LOG"
'
  write_stub yamlfmt '
printf "yamlfmt %s\n" "$*" >> "$STUB_LOG"
'
  write_stub tofu '
printf "tofu %s\n" "$*" >> "$STUB_LOG"
'
}

teardown() {
  teardown_test_env
}

@test "task lint uses the Tuppr Kubernetes target version for deprecation checks" {
  rm -rf "${TEST_TMPDIR}/apps/selfhosted/bad-demo"

  run task --taskfile "${TEST_TMPDIR}/Taskfile.yaml" lint

  [ "$status" -eq 0 ]
  assert_log_contains 'pluto detect-files -d'
  assert_log_contains '--target-versions k8s=v9.9.9 -o wide'

  run grep -c '^pluto detect-files -d ' "${STUB_LOG}"
  [ "$status" -eq 0 ]
  [ "$output" -eq 2 ]
}

@test "task ci runs test before lint" {
  run task --taskfile "${TEST_TMPDIR}/Taskfile.yaml" ci

  [ "$status" -eq 0 ]

  run awk '/^bats tests$/ { print NR; exit }' "${STUB_LOG}"
  [ "$status" -eq 0 ]
  bats_line="$output"

  run awk '/^shellcheck --severity=warning / { print NR; exit }' "${STUB_LOG}"
  [ "$status" -eq 0 ]
  shellcheck_line="$output"

  [ "$bats_line" -lt "$shellcheck_line" ]

  assert_log_contains 'yamllint -c .yamllint .'
  assert_log_contains 'conftest test --no-color --policy '
  assert_log_contains 'pluto detect-files -d '
}

@test "task precommit runs fmt before ci" {
  run task --taskfile "${TEST_TMPDIR}/Taskfile.yaml" precommit

  [ "$status" -eq 0 ]

  run awk '/^prettier --write / { print NR; exit }' "${STUB_LOG}"
  [ "$status" -eq 0 ]
  prettier_line="$output"

  run awk '/^bats tests$/ { print NR; exit }' "${STUB_LOG}"
  [ "$status" -eq 0 ]
  bats_line="$output"

  [ "$prettier_line" -lt "$bats_line" ]
}
