package main

import rego.v1

test_victoria_resources_are_rejected if {
  resource := {
    "apiVersion": "operator.victoriametrics.com/v1beta1",
    "kind": "VMProbe",
    "metadata": {"name": "old-probe"},
  }
  "VMProbe/old-probe uses a retired observability API" in deny with input as resource
}

test_victoria_crds_are_rejected if {
  crd := {
    "kind": "CustomResourceDefinition",
    "metadata": {"name": "vmprobes.operator.victoriametrics.com"},
    "spec": {"group": "operator.victoriametrics.com"},
  }
  "CustomResourceDefinition/vmprobes.operator.victoriametrics.com installs a retired observability API" in deny with input as crd
}

test_prometheus_operator_resources_are_rejected if {
  resource := {
    "apiVersion": "monitoring.coreos.com/v1",
    "kind": "ServiceMonitor",
    "metadata": {"name": "old-scrape"},
  }
  "ServiceMonitor/old-scrape uses a retired observability API" in deny with input as resource
}

test_prometheus_operator_crds_are_rejected if {
  crd := {
    "kind": "CustomResourceDefinition",
    "metadata": {"name": "servicemonitors.monitoring.coreos.com"},
    "spec": {"group": "monitoring.coreos.com"},
  }
  "CustomResourceDefinition/servicemonitors.monitoring.coreos.com installs a retired observability API" in deny with input as crd
}

test_legacy_workloads_are_rejected if {
  workload := {
    "kind": "Deployment",
    "metadata": {"name": "victoria-logs-collector"},
  }
  "Deployment/victoria-logs-collector is a retired observability workload" in deny with input as workload
}

test_gatus_sidecar_is_rejected if {
  workload := {
    "kind": "Deployment",
    "metadata": {"name": "gatus-sidecar"},
  }
  "Deployment/gatus-sidecar is a retired observability workload" in deny with input as workload
}

test_legacy_prometheus_workload_is_rejected if {
  workload := {
    "kind": "StatefulSet",
    "metadata": {"name": "prometheus-kube-prometheus-stack-prometheus"},
  }
  "StatefulSet/prometheus-kube-prometheus-stack-prometheus is a retired observability workload" in deny with input as workload
}

test_sidecar_discovery_annotation_is_rejected if {
  route := {
    "kind": "HTTPRoute",
    "metadata": {
      "name": "service",
      "annotations": {"gatus.home-operations.com/endpoint": "true"},
    },
  }
  "HTTPRoute/service must use explicit Gatus checks" in deny with input as route
}

test_gatus_deployment_is_allowed if {
  workload := {
    "kind": "Deployment",
    "metadata": {"name": "gatus"},
  }
  messages := deny with input as workload
  count(messages) == 0
}
