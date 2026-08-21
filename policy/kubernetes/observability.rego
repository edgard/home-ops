package main

import rego.v1

forbidden_observability_workloads := {
  "alertmanager-kube-prometheus-stack-alertmanager",
  "alloy",
  "kube-prometheus-stack-grafana",
  "loki",
  "prometheus-kube-prometheus-stack-prometheus",
}

allowed_victoria_crds := {
  "vmagents.operator.victoriametrics.com",
  "vmalertmanagerconfigs.operator.victoriametrics.com",
  "vmanomalyconfigs.operator.victoriametrics.com",
  "vmnodescrapes.operator.victoriametrics.com",
  "vmpodscrapes.operator.victoriametrics.com",
  "vmprobes.operator.victoriametrics.com",
  "vmrules.operator.victoriametrics.com",
  "vmscrapeconfigs.operator.victoriametrics.com",
  "vmservicescrapes.operator.victoriametrics.com",
  "vmsingles.operator.victoriametrics.com",
  "vmstaticscrapes.operator.victoriametrics.com",
  "vmusers.operator.victoriametrics.com",
}

required_operator_disable_reconcile_arg := "--controller.disableReconcileFor=AlertmanagerConfig,PodMonitor,Probe,PrometheusRule,ScrapeConfig,ServiceMonitor,VLAgent,VLCluster,VLDistributed,VLogs,VLSingle,VMAlert,VMAlertmanager,VMAlertmanagerConfig,VMAnomaly,VMAnomalyConfig,VMAuth,VMCluster,VMDistributed,VMRule,VMScrapeConfig,VMStaticScrape,VTSingle,VTCluster,VMUser"

indexer_only_victoria_kinds := {
  "VMAlertmanagerConfig",
  "VMAnomalyConfig",
  "VMRule",
  "VMScrapeConfig",
  "VMStaticScrape",
  "VMUser",
}

deny contains msg if {
  startswith(object.get(input, "apiVersion", ""), "monitoring.coreos.com/")
  msg := sprintf("%s/%s must not use Prometheus Operator APIs", [input.kind, input.metadata.name])
}

deny contains msg if {
  input.kind == "CustomResourceDefinition"
  object.get(input.spec, "group", "") == "monitoring.coreos.com"
  msg := sprintf("CustomResourceDefinition/%s must not install Prometheus Operator APIs", [input.metadata.name])
}

deny contains msg if {
  input.kind == "CustomResourceDefinition"
  input.metadata.name in {
    "vmalertmanagers.operator.victoriametrics.com",
    "vmalerts.operator.victoriametrics.com",
  }
  msg := sprintf("CustomResourceDefinition/%s is forbidden; Grafana owns alerting", [input.metadata.name])
}

deny contains msg if {
  input.kind == "Deployment"
  input.metadata.name == "victoria-metrics-k8s-stack-victoria-metrics-operator"
  operator := [container | some container in input.spec.template.spec.containers; container.name == "operator"][0]
  args := object.get(operator, "args", [])
  not required_operator_disable_reconcile_arg in args
  msg := "Deployment/victoria-metrics-k8s-stack-victoria-metrics-operator must disable every controller whose CRD is not installed"
}

deny contains msg if {
  input.kind == "CustomResourceDefinition"
  object.get(input.spec, "group", "") == "operator.victoriametrics.com"
  not allowed_victoria_crds[input.metadata.name]
  msg := sprintf("CustomResourceDefinition/%s is outside the minimal Victoria observability API set", [input.metadata.name])
}

deny contains msg if {
  input.kind == "VMAlert"
  msg := sprintf("VMAlert/%s is forbidden; Grafana owns alert and recording rules", [input.metadata.name])
}

deny contains msg if {
  startswith(object.get(input, "apiVersion", ""), "operator.victoriametrics.com/")
  input.kind in indexer_only_victoria_kinds
  msg := sprintf("%s/%s is forbidden; its CRD is installed only for operator startup compatibility", [input.kind, input.metadata.name])
}

deny contains msg if {
  input.kind in {"Alertmanager", "VMAlertmanager"}
  msg := sprintf("%s/%s is forbidden; Grafana owns notification routing", [input.kind, input.metadata.name])
}

deny contains msg if {
  input.kind == "Prometheus"
  msg := sprintf("Prometheus/%s is forbidden; VMSingle stores metrics", [input.metadata.name])
}

deny contains msg if {
  input.kind in {"Deployment", "StatefulSet", "DaemonSet"}
  forbidden_observability_workloads[input.metadata.name]
  msg := sprintf("%s/%s is forbidden by the Victoria observability architecture", [input.kind, input.metadata.name])
}

deny contains msg if {
  startswith(object.get(input, "apiVersion", ""), "operator.victoriametrics.com/")
  input.kind in {"VMAgent", "VMSingle"}
  spec := object.get(input, "spec", {})
  scrape := object.get(spec, "serviceScrapeSpec", {})
  count(object.get(scrape, "endpoints", [])) == 0
  msg := sprintf("%s/%s must configure a Victoria-native self-scrape", [input.kind, input.metadata.name])
}
