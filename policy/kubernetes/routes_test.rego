package main

import rego.v1

test_httproute_requires_expected_hostname_and_parent_ref if {
  route := {
    "apiVersion": "gateway.networking.k8s.io/v1",
    "kind": "HTTPRoute",
    "metadata": {"name": "demo"},
    "spec": {
      "parentRefs": [{"name": "other", "namespace": "platform-system", "sectionName": "https"}],
      "hostnames": ["demo.example.com"],
    },
  }
  "HTTPRoute/demo hostname demo.example.com must end with .edgard.org" in deny with input as route
  "HTTPRoute/demo must target gateway/platform-system section https" in deny with input as route
}

test_httproute_allows_unannotated_routes if {
  route := {
    "apiVersion": "gateway.networking.k8s.io/v1",
    "kind": "HTTPRoute",
    "metadata": {"name": "demo"},
    "spec": {
      "parentRefs": [{"name": "gateway", "namespace": "platform-system", "sectionName": "https"}],
      "hostnames": ["demo.edgard.org"],
    },
  }

  results := deny with input as route
  count(results) == 0
}

test_legacy_external_dns_annotations_are_rejected_on_any_resource if {
  service := {
    "apiVersion": "v1",
    "kind": "Service",
    "metadata": {
      "name": "demo",
      "namespace": "platform-system",
      "annotations": {
        "external-dns.alpha.kubernetes.io/target": "192.168.1.241",
      },
    },
  }

  "Service/demo uses retired ExternalDNS annotation external-dns.alpha.kubernetes.io/target" in deny with input as service
}

test_shared_gateway_requires_modern_lan_target if {
  gateway := {
    "apiVersion": "gateway.networking.k8s.io/v1",
    "kind": "Gateway",
    "metadata": {
      "name": "gateway",
      "namespace": "platform-system",
      "annotations": {
        "external-dns.alpha.kubernetes.io/target": "192.168.1.241",
      },
    },
  }

  "Gateway/gateway must set external-dns.kubernetes.io/target to 192.168.1.241" in deny with input as gateway
}

test_shared_gateway_allows_modern_lan_target if {
  gateway := {
    "apiVersion": "gateway.networking.k8s.io/v1",
    "kind": "Gateway",
    "metadata": {
      "name": "gateway",
      "namespace": "platform-system",
      "annotations": {
        "external-dns.kubernetes.io/target": "192.168.1.241",
      },
    },
  }

  results := deny with input as gateway
  count(results) == 0
}
