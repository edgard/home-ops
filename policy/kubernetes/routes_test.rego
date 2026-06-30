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
