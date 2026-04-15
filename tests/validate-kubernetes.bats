#!/usr/bin/env bats

load 'helpers/test_helper.bash'

setup() {
  setup_test_env

  write_stub yq '
printf "yq %s\n" "$*" >> "$STUB_LOG"
if [[ "${FAIL_YQ_CRD:-}" == "1" && "$1" == "-r" ]]; then
  exit 1
fi
if [[ "$2" == ".chart.repo" ]]; then
  awk "/repo:/{print \$2; exit}" "$3"
elif [[ "$2" == ".chart.version" ]]; then
  awk "/version:/{print \$2; exit}" "$3"
elif [[ "$2" == ".chart.name" ]]; then
  awk "/name:/{print \$2; exit}" "$3"
elif [[ "$2" == ".spec.kubernetes.version // \"\"" ]]; then
  awk "/version:/{print \$2; exit}" "$3"
else
  :
fi
'
  write_stub helm '
printf "helm %s\n" "$*" >> "$STUB_LOG"
if [[ "${REQUIRE_HELM_STATE_ISOLATION:-}" == "1" ]]; then
  for var in HELM_CONFIG_HOME HELM_CACHE_HOME HELM_DATA_HOME HELM_REPOSITORY_CONFIG HELM_REPOSITORY_CACHE HELM_REGISTRY_CONFIG HELM_CONTENT_CACHE; do
    value="${!var:-}"
    if [[ -z "$value" || "$value" == "${HOME}"* ]]; then
      echo "unisolated ${var}=${value}" >&2
      exit 1
    fi
  done
fi
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
if [[ "$1" == "template" && "${FAIL_HELM_TEMPLATE:-}" == "1" ]]; then
  exit 1
fi
'
  write_stub pluto '
printf "pluto %s\n" "$*" >> "$STUB_LOG"
: 
'
  write_stub kubeconform '
printf "kubeconform %s\n" "$*" >> "$STUB_LOG"
: 
'
  write_stub conftest '
printf "conftest %s\n" "$*" >> "$STUB_LOG"
if [[ -n "${CAPTURE_CONTFEST_INPUT:-}" ]]; then
  cp "${@: -1}" "$CAPTURE_CONTFEST_INPUT"
fi
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
  version: 4.5.6
EOF
  cat > "${TEST_TMPDIR}/apps/selfhosted/http-demo/values.yaml" <<EOF
---
service:
  main:
    enabled: true
EOF

  mkdir -p "${TEST_TMPDIR}/apps/selfhosted/demo-copy"
  cat > "${TEST_TMPDIR}/apps/selfhosted/demo-copy/app.yaml" <<EOF
---
chart:
  repo: oci://ghcr.io/example/app-template
  version: 1.2.3
EOF
  cat > "${TEST_TMPDIR}/apps/selfhosted/demo-copy/values.yaml" <<EOF
---
service:
  main:
    enabled: true
EOF

  mkdir -p "${TEST_TMPDIR}/external-one/demo"
  cat > "${TEST_TMPDIR}/external-one/demo/app.yaml" <<EOF
---
chart:
  repo: oci://ghcr.io/example/app-template
  version: 1.2.3
EOF
  cat > "${TEST_TMPDIR}/external-one/demo/values.yaml" <<EOF
---
service:
  main:
    enabled: true
EOF

  mkdir -p "${TEST_TMPDIR}/external-two/demo"
  cat > "${TEST_TMPDIR}/external-two/demo/app.yaml" <<EOF
---
chart:
  repo: oci://ghcr.io/example/app-template
  version: 1.2.3
EOF
  cat > "${TEST_TMPDIR}/external-two/demo/values.yaml" <<EOF
---
service:
  main:
    enabled: true
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

  mkdir -p "${TEST_TMPDIR}/apps/selfhosted/demo/manifests"
  cat > "${TEST_TMPDIR}/apps/selfhosted/demo/manifests/demo.configmap.yaml" <<EOF
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: demo
  namespace: default
EOF

  mkdir -p "${TEST_TMPDIR}/apps/platform-system/tuppr/manifests"
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

  mkdir -p "${TEST_TMPDIR}/apps/platform-system/gateway-api/manifests"
  : > "${TEST_TMPDIR}/apps/platform-system/gateway-api/manifests/gateway-api-crds.yaml"

  mkdir -p "${TEST_TMPDIR}/apps/platform-system/homelab-controller/manifests"
  : > "${TEST_TMPDIR}/apps/platform-system/homelab-controller/manifests/homelab-controller-gatusconfigs.customresourcedefinition.yaml"
}

teardown() {
  teardown_test_env
}

@test "validate-kubernetes helm-apps fails when helm rendering fails" {
  run env FAIL_HELM_TEMPLATE=1 bash scripts/validate-kubernetes.sh helm-apps "${TEST_TMPDIR}/apps/selfhosted/demo/app.yaml"

  [ "$status" -ne 0 ]
  [[ "$output" == *"Failed: ${TEST_TMPDIR}/apps/selfhosted/demo"* ]]
}

@test "validate-kubernetes helm-apps derives Kubernetes target version from Tuppr manifest" {
  run env REPO_ROOT="${TEST_TMPDIR}" bash scripts/validate-kubernetes.sh helm-apps "${TEST_TMPDIR}/apps/selfhosted/demo/app.yaml"

  [ "$status" -eq 0 ]
  assert_log_contains 'conftest test --no-color --parser yaml --policy'
  assert_log_contains 'kubeconform -kubernetes-version 9.9.9'
  assert_log_contains 'pluto detect-files -d '
  assert_log_contains '--target-versions k8s=v9.9.9 -o wide'
  assert_log_contains '--kube-version 9.9.9'
}

@test "validate-kubernetes helm-apps renders each app once and reuses the output" {
  run env REPO_ROOT="${TEST_TMPDIR}" bash scripts/validate-kubernetes.sh helm-apps "${TEST_TMPDIR}/apps/selfhosted/demo/app.yaml"

  [ "$status" -eq 0 ]
  run grep -c '^helm template ' "${STUB_LOG}"
  [ "$status" -eq 0 ]
  [ "$output" -eq 1 ]
}

@test "validate-kubernetes helm-apps pulls a shared chart once for matching apps" {
  run env REPO_ROOT="${TEST_TMPDIR}" bash scripts/validate-kubernetes.sh helm-apps \
    "${TEST_TMPDIR}/apps/selfhosted/demo/app.yaml" \
    "${TEST_TMPDIR}/apps/selfhosted/demo-copy/app.yaml"

  [ "$status" -eq 0 ]
  run grep -c '^helm pull oci://ghcr.io/example/app-template --version 1.2.3 --untar --untardir ' "${STUB_LOG}"
  [ "$status" -eq 0 ]
  [ "$output" -eq 1 ]

  run grep -c '^helm template ' "${STUB_LOG}"
  [ "$status" -eq 0 ]
  [ "$output" -eq 2 ]
}

@test "validate-kubernetes helm-apps batches rendered policy, schema, and deprecation checks" {
  run env REPO_ROOT="${TEST_TMPDIR}" bash scripts/validate-kubernetes.sh helm-apps \
    "${TEST_TMPDIR}/apps/selfhosted/demo/app.yaml" \
    "${TEST_TMPDIR}/apps/selfhosted/demo-copy/app.yaml"

  [ "$status" -eq 0 ]

  run grep -c '^conftest test --no-color --parser yaml --policy ' "${STUB_LOG}"
  [ "$status" -eq 0 ]
  [ "$output" -eq 1 ]

  run grep -c '^kubeconform -kubernetes-version 9.9.9 ' "${STUB_LOG}"
  [ "$status" -eq 0 ]
  [ "$output" -eq 1 ]

  run grep -c '^pluto detect-files -d ' "${STUB_LOG}"
  [ "$status" -eq 0 ]
  [ "$output" -eq 1 ]
}

@test "validate-kubernetes helm-apps keeps distinct rendered paths for same-named external apps" {
  run env REPO_ROOT="${TEST_TMPDIR}" bash scripts/validate-kubernetes.sh helm-apps \
    "${TEST_TMPDIR}/external-one/demo/app.yaml" \
    "${TEST_TMPDIR}/external-two/demo/app.yaml"

  [ "$status" -eq 0 ]
  assert_log_contains 'external-one/demo.yaml'
  assert_log_contains 'external-two/demo.yaml'
}

@test "validate-kubernetes manifests derives Kubernetes target version from Tuppr manifest" {
  run env REPO_ROOT="${TEST_TMPDIR}" bash scripts/validate-kubernetes.sh manifests

  [ "$status" -eq 0 ]
  assert_log_contains 'kubeconform -kubernetes-version 9.9.9'
}

@test "validate-kubernetes metadata does not build the schema catalog" {
  run env FAIL_YQ_CRD=1 REPO_ROOT="${TEST_TMPDIR}" bash scripts/validate-kubernetes.sh metadata

  [ "$status" -eq 0 ]
  run grep -c '^yq -r ' "${STUB_LOG}"
  [ "$status" -eq 1 ]
}

@test "validate-kubernetes policies does not build the schema catalog" {
  run env FAIL_YQ_CRD=1 REPO_ROOT="${TEST_TMPDIR}" bash scripts/validate-kubernetes.sh policies

  [ "$status" -eq 0 ]
  run grep -c '^yq -r ' "${STUB_LOG}"
  [ "$status" -eq 1 ]
}

@test "validate-kubernetes source runs source policy without kubernetes compatibility checks" {
  run env REPO_ROOT="${TEST_TMPDIR}" bash scripts/validate-kubernetes.sh source

  [ "$status" -eq 0 ]
  assert_log_contains 'conftest test --no-color --policy '

  run grep -F 'policy/source' "${STUB_LOG}"
  [ "$status" -eq 0 ]

  run grep -c '^kubeconform ' "${STUB_LOG}"
  [ "$status" -eq 1 ]

  run grep -c '^pluto ' "${STUB_LOG}"
  [ "$status" -eq 1 ]

  run grep -c '.spec.kubernetes.version // ""' "${STUB_LOG}"
  [ "$status" -eq 1 ]
}

@test "validate-kubernetes source tolerates missing values files and still builds the inventory" {
  mkdir -p "${TEST_TMPDIR}/apps/selfhosted/no-values"
  cat > "${TEST_TMPDIR}/apps/selfhosted/no-values/app.yaml" <<EOF
---
chart:
  repo: oci://ghcr.io/bjw-s-labs/helm/app-template
  version: 4.6.2
sync:
  wave: "0"
EOF

  inventory="${TEST_TMPDIR}/captured-source.yaml"
  run env REPO_ROOT="${TEST_TMPDIR}" CAPTURE_CONTFEST_INPUT="${inventory}" bash scripts/validate-kubernetes.sh source

  [ "$status" -eq 0 ]
  [[ "$output" != *"awk:"* ]]

  run grep -F "${TEST_TMPDIR}/apps/selfhosted/no-values/app.yaml" "${inventory}"
  [ "$status" -eq 0 ]
}

@test "validate-kubernetes source inventories root argocd manifests" {
  inventory="${TEST_TMPDIR}/captured-source.yaml"
  run env REPO_ROOT="${TEST_TMPDIR}" CAPTURE_CONTFEST_INPUT="${inventory}" bash scripts/validate-kubernetes.sh source

  [ "$status" -eq 0 ]

  run grep -F "${TEST_TMPDIR}/argocd/projects/demo.appproject.yaml" "${inventory}"
  [ "$status" -eq 0 ]

  run grep -F "relative_path: 'argocd/projects/demo.appproject.yaml'" "${inventory}"
  [ "$status" -eq 0 ]

  run grep -F "basename: 'demo.appproject.yaml'" "${inventory}"
  [ "$status" -eq 0 ]
}

@test "validate-kubernetes helm-apps skips target version lookup when no apps are provided" {
  rm -rf "${TEST_TMPDIR}/apps/platform-system/tuppr"

  run env REPO_ROOT="${TEST_TMPDIR}" bash scripts/validate-kubernetes.sh helm-apps

  [ "$status" -eq 0 ]
}

@test "validate-kubernetes helm-apps adds and updates non-OCI Helm repos before rendering" {
  run env REPO_ROOT="${TEST_TMPDIR}" bash scripts/validate-kubernetes.sh helm-apps "${TEST_TMPDIR}/apps/selfhosted/http-demo/app.yaml"

  [ "$status" -eq 0 ]
  assert_log_contains 'helm repo add abcd1234 https://charts.example.com'
  assert_log_contains 'helm repo update abcd1234'
  assert_log_contains 'helm pull abcd1234/demo --version 4.5.6 --untar --untardir'
  assert_log_contains 'helm template test '
}

@test "validate-kubernetes helm-apps isolates helm state during rendering" {
  run env REQUIRE_HELM_STATE_ISOLATION=1 REPO_ROOT="${TEST_TMPDIR}" bash scripts/validate-kubernetes.sh helm-apps "${TEST_TMPDIR}/apps/selfhosted/http-demo/app.yaml"

  [ "$status" -eq 0 ]
  assert_log_contains 'helm repo add abcd1234 https://charts.example.com'
  assert_log_contains 'helm repo update abcd1234'
  assert_log_contains 'helm pull abcd1234/demo --version 4.5.6 --untar --untardir'
  assert_log_contains 'helm template test '
}

@test "validate-kubernetes fails cleanly when Tuppr manifest is missing" {
  rm -rf "${TEST_TMPDIR}/apps/platform-system/tuppr"

  run env REPO_ROOT="${TEST_TMPDIR}" bash scripts/validate-kubernetes.sh manifests

  [ "$status" -ne 0 ]
  [[ "$output" == *"Missing Kubernetes upgrade manifest:"* ]]
}

@test "validate-kubernetes fails cleanly when Tuppr manifest has no Kubernetes version" {
  cat > "${TEST_TMPDIR}/apps/platform-system/tuppr/manifests/tuppr-kubernetes.kubernetesupgrade.yaml" <<EOF
---
apiVersion: tuppr.home-operations.com/v1alpha1
kind: KubernetesUpgrade
metadata:
  name: kubernetes
spec:
  kubernetes: {}
EOF

  run env REPO_ROOT="${TEST_TMPDIR}" bash scripts/validate-kubernetes.sh manifests

  [ "$status" -ne 0 ]
  [[ "$output" == *"Missing spec.kubernetes.version"* ]]
}
