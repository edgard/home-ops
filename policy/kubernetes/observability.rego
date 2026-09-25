package main

import rego.v1

legacy_observability_api_groups := {
  "monitoring.coreos.com",
  "operator.victoriametrics.com",
}

legacy_observability_workload_prefixes := {
  "alertmanager-kube-prometheus-stack-alertmanager",
  "alloy",
  "gatus-sidecar",
  "kube-prometheus-stack-grafana",
  "loki",
  "prometheus-blackbox-exporter",
  "prometheus-kube-prometheus-stack-prometheus",
  "victoria-logs-",
  "victoria-metrics-k8s-stack-",
  "vmagent-victoria-metrics-k8s-stack",
  "vmsingle-victoria-metrics-k8s-stack",
}

deny contains msg if {
  group := split(object.get(input, "apiVersion", ""), "/")[0]
  group in legacy_observability_api_groups
  msg := sprintf("%s/%s uses a retired observability API", [input.kind, input.metadata.name])
}

deny contains msg if {
  input.kind == "CustomResourceDefinition"
  object.get(input.spec, "group", "") in legacy_observability_api_groups
  msg := sprintf("CustomResourceDefinition/%s installs a retired observability API", [input.metadata.name])
}

deny contains msg if {
  input.kind in {"Deployment", "StatefulSet", "DaemonSet"}
  some prefix in legacy_observability_workload_prefixes
  startswith(input.metadata.name, prefix)
  msg := sprintf("%s/%s is a retired observability workload", [input.kind, input.metadata.name])
}

deny contains msg if {
  annotations := object.get(input.metadata, "annotations", {})
  object.get(annotations, "gatus.home-operations.com/endpoint", null) != null
  msg := sprintf("%s/%s must use explicit Gatus checks", [input.kind, input.metadata.name])
}
