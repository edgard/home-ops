package main

import rego.v1

test_prometheus_operator_resources_are_rejected if {
  resource := {
    "apiVersion": "monitoring.coreos.com/v1",
    "kind": "ServiceMonitor",
    "metadata": {"name": "legacy"},
    "spec": {},
  }
  "ServiceMonitor/legacy must not use Prometheus Operator APIs" in deny with input as resource
}

test_prometheus_operator_crds_are_rejected if {
  crd := {
    "apiVersion": "apiextensions.k8s.io/v1",
    "kind": "CustomResourceDefinition",
    "metadata": {"name": "servicemonitors.monitoring.coreos.com"},
    "spec": {"group": "monitoring.coreos.com"},
  }
  "CustomResourceDefinition/servicemonitors.monitoring.coreos.com must not install Prometheus Operator APIs" in deny with input as crd
}

test_victoria_alerting_crds_are_rejected if {
  some name in {
    "vmalertmanagers.operator.victoriametrics.com",
    "vmalerts.operator.victoriametrics.com",
  }
  crd := {
    "apiVersion": "apiextensions.k8s.io/v1",
    "kind": "CustomResourceDefinition",
    "metadata": {"name": name},
    "spec": {"group": "operator.victoriametrics.com"},
  }
  sprintf("CustomResourceDefinition/%s is forbidden; Grafana owns alerting", [name]) in deny with input as crd
}

test_operator_without_selective_controller_argument_is_rejected if {
  deployment := {
    "apiVersion": "apps/v1",
    "kind": "Deployment",
    "metadata": {"name": "victoria-metrics-k8s-stack-victoria-metrics-operator"},
    "spec": {"template": {"spec": {"containers": [{
      "name": "operator",
      "args": ["--leader-elect"],
    }]}}},
  }
  "Deployment/victoria-metrics-k8s-stack-victoria-metrics-operator must disable every controller whose CRD is not installed" in deny with input as deployment
}

test_operator_with_selective_controller_argument_is_allowed if {
  deployment := {
    "apiVersion": "apps/v1",
    "kind": "Deployment",
    "metadata": {"name": "victoria-metrics-k8s-stack-victoria-metrics-operator"},
    "spec": {"template": {"spec": {"containers": [{
      "name": "operator",
      "args": [required_operator_disable_reconcile_arg],
    }]}}},
  }
  results := deny with input as deployment
  count(results) == 0
}

test_indexer_only_victoria_resources_are_rejected if {
  some kind in indexer_only_victoria_kinds
  resource := {
    "apiVersion": "operator.victoriametrics.com/v1beta1",
    "kind": kind,
    "metadata": {"name": "unused"},
    "spec": {},
  }
  sprintf("%s/unused is forbidden; its CRD is installed only for operator startup compatibility", [kind]) in deny with input as resource
}

test_unneeded_victoria_crds_are_rejected if {
  crd := {
    "apiVersion": "apiextensions.k8s.io/v1",
    "kind": "CustomResourceDefinition",
    "metadata": {"name": "vmclusters.operator.victoriametrics.com"},
    "spec": {"group": "operator.victoriametrics.com"},
  }
  "CustomResourceDefinition/vmclusters.operator.victoriametrics.com is outside the minimal Victoria observability API set" in deny with input as crd
}

test_required_victoria_crds_are_allowed if {
  every name in allowed_victoria_crds {
    crd := {
      "apiVersion": "apiextensions.k8s.io/v1",
      "kind": "CustomResourceDefinition",
    "metadata": {"name": name},
    "spec": {"group": "operator.victoriametrics.com"},
  }
    results := deny with input as crd
    count(results) == 0
  }
}

test_external_rule_and_notification_components_are_rejected if {
  vmalert := {
    "apiVersion": "operator.victoriametrics.com/v1beta1",
    "kind": "VMAlert",
    "metadata": {"name": "external-ruler"},
    "spec": {},
  }
  alertmanager := {
    "apiVersion": "operator.victoriametrics.com/v1beta1",
    "kind": "VMAlertmanager",
    "metadata": {"name": "external-router"},
    "spec": {},
  }
  prometheus := {
    "apiVersion": "monitoring.coreos.com/v1",
    "kind": "Prometheus",
    "metadata": {"name": "standalone-metrics"},
    "spec": {},
  }
  standalone_alertmanager := {
    "apiVersion": "monitoring.coreos.com/v1",
    "kind": "Alertmanager",
    "metadata": {"name": "standalone-router"},
    "spec": {},
  }
  "VMAlert/external-ruler is forbidden; Grafana owns alert and recording rules" in deny with input as vmalert
  "VMAlertmanager/external-router is forbidden; Grafana owns notification routing" in deny with input as alertmanager
  "Prometheus/standalone-metrics is forbidden; VMSingle stores metrics" in deny with input as prometheus
  "Alertmanager/standalone-router is forbidden; Grafana owns notification routing" in deny with input as standalone_alertmanager
}

test_forbidden_loki_and_alloy_workloads_are_rejected if {
  loki := {
    "apiVersion": "apps/v1",
    "kind": "StatefulSet",
    "metadata": {"name": "loki"},
    "spec": {},
  }
  alloy := {
    "apiVersion": "apps/v1",
    "kind": "StatefulSet",
    "metadata": {"name": "alloy"},
    "spec": {},
  }
  "StatefulSet/loki is forbidden by the Victoria observability architecture" in deny with input as loki
  "StatefulSet/alloy is forbidden by the Victoria observability architecture" in deny with input as alloy
}

test_victoria_native_scrapes_are_allowed if {
  scrape := {
    "apiVersion": "operator.victoriametrics.com/v1beta1",
    "kind": "VMServiceScrape",
    "metadata": {"name": "native"},
    "spec": {},
  }
  results := deny with input as scrape
  count(results) == 0
}

test_primary_victoria_components_require_self_scraping if {
  some kind in {"VMAgent", "VMSingle"}
  component := {
    "apiVersion": "operator.victoriametrics.com/v1beta1",
    "kind": kind,
    "metadata": {"name": "primary"},
    "spec": {},
  }
  sprintf("%s/primary must configure a Victoria-native self-scrape", [kind]) in deny with input as component
}
