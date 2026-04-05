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
cat >/dev/null
'
  write_stub pluto '
printf "pluto %s\n" "$*" >> "$STUB_LOG"
cat >/dev/null
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

@test "task surface excludes one-off validation tasks and exposes ci/precommit" {
  run grep -F 'validate:metadata:' "${BATS_TEST_DIRNAME}/../Taskfile.yaml"
  [ "$status" -eq 1 ]

  run grep -F 'validate:server:' "${BATS_TEST_DIRNAME}/../Taskfile.yaml"
  [ "$status" -eq 1 ]

  run grep -F 'ci:' "${BATS_TEST_DIRNAME}/../Taskfile.yaml"
  [ "$status" -eq 0 ]

  run grep -F 'precommit:' "${BATS_TEST_DIRNAME}/../Taskfile.yaml"
  [ "$status" -eq 0 ]

  run grep -F -- '--target-versions k8s=v1.35.1' "${BATS_TEST_DIRNAME}/../Taskfile.yaml"
  [ "$status" -eq 1 ]
}

@test "validate-kubernetes compatibility entrypoint no longer exposes server validation" {
  run grep -F 'server)' "${BATS_TEST_DIRNAME}/../scripts/validate-kubernetes.sh"
  [ "$status" -eq 1 ]

  run grep -F '|server>' "${BATS_TEST_DIRNAME}/../scripts/validate-kubernetes.sh"
  [ "$status" -eq 1 ]
}

@test "validation helpers are folded into the main validation entrypoint" {
  [ ! -f "${BATS_TEST_DIRNAME}/../scripts/kubernetes-target-version.sh" ]
  [ ! -f "${BATS_TEST_DIRNAME}/../scripts/render-helm-app.sh" ]
  [ ! -f "${BATS_TEST_DIRNAME}/../scripts/validate-app-metadata.sh" ]
}

@test "task ci combines test and lint and precommit adds fmt" {
  run grep -F 'task: test' "${BATS_TEST_DIRNAME}/../Taskfile.yaml"
  [ "$status" -eq 0 ]

  run grep -F 'task: lint' "${BATS_TEST_DIRNAME}/../Taskfile.yaml"
  [ "$status" -eq 0 ]

  run grep -F 'task: fmt' "${BATS_TEST_DIRNAME}/../Taskfile.yaml"
  [ "$status" -eq 0 ]

  run grep -F 'task: ci' "${BATS_TEST_DIRNAME}/../Taskfile.yaml"
  [ "$status" -eq 0 ]
}

@test "task lint still includes metadata validation in the offline gate" {
  run grep -F '"{{.TASKFILE_DIR}}/scripts/validate-kubernetes.sh" metadata' "${BATS_TEST_DIRNAME}/../Taskfile.yaml"

  [ "$status" -eq 0 ]
}

@test "task lint includes raw and rendered policy validation" {
  run grep -F '"{{.TASKFILE_DIR}}/scripts/validate-kubernetes.sh" policies' "${BATS_TEST_DIRNAME}/../Taskfile.yaml"
  [ "$status" -eq 0 ]

  run grep -F '"{{.TASKFILE_DIR}}/scripts/validate-kubernetes.sh" helm-apps "${files[@]}"' "${BATS_TEST_DIRNAME}/../Taskfile.yaml"
  [ "$status" -eq 0 ]

  run grep -F '"{{.TASKFILE_DIR}}/scripts/validate-kubernetes.sh" rendered-policies' "${BATS_TEST_DIRNAME}/../Taskfile.yaml"
  [ "$status" -eq 1 ]

  run grep -F '"{{.TASKFILE_DIR}}/scripts/validate-kubernetes.sh" rendered-manifests' "${BATS_TEST_DIRNAME}/../Taskfile.yaml"
  [ "$status" -eq 1 ]

  run grep -F '"{{.TASKFILE_DIR}}/scripts/validate-kubernetes.sh" rendered-deprecations' "${BATS_TEST_DIRNAME}/../Taskfile.yaml"
  [ "$status" -eq 1 ]
}
