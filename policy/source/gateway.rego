package main

import rego.v1

gateway_target_matches if {
  some cidr in input.gateway.lan_cidrs
  net.cidr_contains(cidr, input.gateway.dns_target)
  split(cidr, "/")[0] == input.gateway.dns_target
}

deny contains "Gateway DNS target must match its configured Multus LAN address" if {
  input.gateway
  not gateway_target_matches
}
