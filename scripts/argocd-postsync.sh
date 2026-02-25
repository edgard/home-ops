#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"
wait_medium="${BOOTSTRAP_WAIT_MEDIUM:-120s}"
wait_long="${BOOTSTRAP_WAIT_LONG:-180s}"

kubectl apply -f "${repo_root}/apps/argocd/argocd/manifests/argocd-repo-credentials.externalsecret.yaml"
kubectl wait --for=condition=Ready --timeout="${wait_medium}" externalsecret/argocd-repo-credentials -n argocd
kubectl wait --for=condition=Established --timeout="${wait_long}" crd/applications.argoproj.io crd/appprojects.argoproj.io crd/applicationsets.argoproj.io
kubectl apply -f "${repo_root}/argocd/root.app.yaml"
