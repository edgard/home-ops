#!/usr/bin/env bats

load 'helpers/test_helper.bash'

setup() {
  setup_test_env

  write_stub yq '
printf "yq %s\n" "$*" >> "$STUB_LOG"
if [[ "$2" == ".chart.repo" ]]; then
  awk "/repo:/{print \$2; exit}" "$3"
elif [[ "$2" == ".chart.version" ]]; then
  awk "/version:/{print \$2; exit}" "$3"
elif [[ "$2" == ".chart.name" ]]; then
  awk "/name:/{print \$2; exit}" "$3"
else
  :
fi
'
  write_stub helm '
printf "helm %s\n" "$*" >> "$STUB_LOG"
if [[ "${FAIL_HELM_TEMPLATE:-}" == "1" ]]; then
  exit 1
fi
'
  write_stub pluto '
printf "pluto %s\n" "$*" >> "$STUB_LOG"
cat >/dev/null
if [[ "${FAIL_PLUTO_DETECT:-}" == "1" ]]; then
  exit 1
fi
'
  write_stub kubeconform '
printf "kubeconform %s\n" "$*" >> "$STUB_LOG"
cat >/dev/null
if [[ "${FAIL_KUBECONFORM:-}" == "1" ]]; then
  exit 1
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
}

teardown() {
  teardown_test_env
}

@test "validate-kubernetes helm-apps templates charts, schema-validates, and runs pluto" {
  run bash scripts/validate-kubernetes.sh helm-apps "${TEST_TMPDIR}/apps/selfhosted/demo/app.yaml"

  [ "$status" -eq 0 ]
  assert_log_contains "helm template test oci://ghcr.io/example/app-template --version 1.2.3 --values ${TEST_TMPDIR}/apps/selfhosted/demo/values.yaml --api-versions gateway.networking.k8s.io/v1/HTTPRoute"
  assert_log_contains "kubeconform -kubernetes-version 1.35.1"
  assert_log_contains "-skip CustomResourceDefinition"
  assert_log_contains "-schema-location default -schema-location https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json"
  assert_log_contains "pluto detect - --target-versions k8s=v1.35.1 -o wide"
}

@test "validate-kubernetes manifests validates raw manifests with kubeconform" {
  run env REPO_ROOT="${TEST_TMPDIR}" bash scripts/validate-kubernetes.sh manifests

  [ "$status" -eq 0 ]
  assert_log_contains "kubeconform -kubernetes-version 1.35.1"
  assert_log_contains "-schema-location default -schema-location https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json -skip CustomResourceDefinition,renovate-operator.mogenius.com/v1alpha1/RenovateJob ${TEST_TMPDIR}/argocd ${TEST_TMPDIR}/apps/selfhosted/demo/manifests"
}

@test "validate-kubernetes helm-apps fails when helm rendering fails" {
  run env FAIL_HELM_TEMPLATE=1 bash scripts/validate-kubernetes.sh helm-apps "${TEST_TMPDIR}/apps/selfhosted/demo/app.yaml"

  [ "$status" -ne 0 ]
  [[ "$output" == *"Failed: ${TEST_TMPDIR}/apps/selfhosted/demo"* ]]
}

@test "validate-kubernetes helm-apps fails when kubeconform fails" {
  run env FAIL_KUBECONFORM=1 bash scripts/validate-kubernetes.sh helm-apps "${TEST_TMPDIR}/apps/selfhosted/demo/app.yaml"

  [ "$status" -ne 0 ]
  [[ "$output" == *"Failed: ${TEST_TMPDIR}/apps/selfhosted/demo"* ]]
}

@test "validate-kubernetes helm-apps fails when pluto fails" {
  run env FAIL_PLUTO_DETECT=1 bash scripts/validate-kubernetes.sh helm-apps "${TEST_TMPDIR}/apps/selfhosted/demo/app.yaml"

  [ "$status" -ne 0 ]
  [[ "$output" == *"Failed: ${TEST_TMPDIR}/apps/selfhosted/demo"* ]]
}
