package main

import rego.v1

test_gateway_address_can_change_with_its_network if {
  results := deny with input as {"gateway": {"dns_target": "192.0.2.25", "lan_cidrs": ["192.0.2.25/24"]}}
  count(results) == 0
}

test_gateway_dns_must_match_its_network if {
  "Gateway DNS target must match its configured Multus LAN address" in deny with input as {"gateway": {"dns_target": "192.0.2.26", "lan_cidrs": ["192.0.2.25/24"]}}
}
