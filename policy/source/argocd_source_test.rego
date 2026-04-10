package main

import rego.v1

test_rejects_argocd_raw_httproute_manifests if {
  app := {
    "app_file": "/repo/apps/argocd/argocd/app.yaml",
    "values_file": "/repo/apps/argocd/argocd/values.yaml",
    "chart_repo": "oci://ghcr.io/argoproj/argo-helm/argo-cd",
    "chart_version": "9.4.17",
    "raw_httproute_manifest_paths": ["/repo/apps/argocd/argocd/manifests/argocd.httproute.yaml"],
  }

  "argo-cd chart apps must declare HTTPRoute via values.yaml server.httproute instead of a raw manifest in /repo/apps/argocd/argocd/values.yaml" in deny with input as {"apps": [app], "manifests": [valid_manifest]}
}
