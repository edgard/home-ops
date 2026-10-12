package main

import rego.v1

route_coverage_fixture := {
	"route_hosts": ["app.edgard.org", "status.edgard.org", "app.edgard.org"],
	"excluded_hosts": ["status.edgard.org"],
	"http_hosts": ["app.edgard.org"],
}

test_route_coverage_accepts_deduplicated_routes if {
	results := deny with input as {"route_coverage": route_coverage_fixture}
	count(results) == 0
}

test_route_coverage_rejects_missing if {
	coverage := object.union(route_coverage_fixture, {"http_hosts": []})
	results := deny with input as {"route_coverage": coverage}
	count(results) > 0
}

test_route_coverage_rejects_obsolete if {
	coverage := object.union(route_coverage_fixture, {"http_hosts": ["app.edgard.org", "old.edgard.org"]})
	results := deny with input as {"route_coverage": coverage}
	count(results) > 0
}

test_route_coverage_rejects_duplicates if {
	coverage := object.union(route_coverage_fixture, {"http_hosts": ["app.edgard.org", "app.edgard.org"]})
	results := deny with input as {"route_coverage": coverage}
	count(results) > 0
}

test_route_coverage_requires_inventory_shape if {
	every coverage in [null, {}, {"route_hosts": "app", "http_hosts": [], "excluded_hosts": []}, {"route_hosts": [], "http_hosts": [null], "excluded_hosts": []}] {
		results := deny with input as {"route_coverage": coverage}
		count(results) > 0
	}
}

test_route_coverage_does_not_apply_to_manifests if {
	results := deny with input as {"kind": "ConfigMap", "metadata": {"name": "demo"}}
	count(results) == 0
}
