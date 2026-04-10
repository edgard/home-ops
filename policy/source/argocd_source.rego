package main

import rego.v1

deny contains msg if {
  some app in input.apps
  is_argocd_chart(app)
  count(object.get(app, "raw_httproute_manifest_paths", [])) > 0
  msg := sprintf("argo-cd chart apps must declare HTTPRoute via values.yaml server.httproute instead of a raw manifest in %s", [app.values_file])
}

is_argocd_chart(app) if {
  app.chart_repo == "oci://ghcr.io/argoproj/argo-helm/argo-cd"
}
