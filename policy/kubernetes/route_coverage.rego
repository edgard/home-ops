package main

import rego.v1

# Only aggregate route inventories enter this policy; raw/rendered manifests
# continue to use their normal workload guardrails.
route_coverage_inventory_present if {
	"route_coverage" in object.keys(input)
}

valid_route_coverage_inventory if {
	coverage := input.route_coverage
	every key in ["route_hosts", "excluded_hosts", "http_hosts"] {
		hosts := coverage[key]
		is_array(hosts)
		every host in hosts {
			is_string(host)
			host != ""
		}
	}
}

deny contains "Gatus route coverage inventory must contain arrays of nonempty hostnames" if {
	route_coverage_inventory_present
	not valid_route_coverage_inventory
}

route_coverage_expected := {host |
	valid_route_coverage_inventory
	some host in input.route_coverage.route_hosts
	not host in input.route_coverage.excluded_hosts
}

route_coverage_actual := {host |
	valid_route_coverage_inventory
	some host in input.route_coverage.http_hosts
}

deny contains msg if {
	valid_route_coverage_inventory
	some host in (route_coverage_expected - route_coverage_actual)
	msg := sprintf("Gatus is missing routed application %s", [host])
}

deny contains msg if {
	valid_route_coverage_inventory
	some host in (route_coverage_actual - route_coverage_expected)
	msg := sprintf("Gatus has obsolete HTTP target %s", [host])
}

deny contains msg if {
	valid_route_coverage_inventory
	some host in route_coverage_actual
	duplicates := [entry | some entry in input.route_coverage.http_hosts; entry == host]
	count(duplicates) > 1
	msg := sprintf("Gatus has duplicate HTTP target %s", [host])
}
