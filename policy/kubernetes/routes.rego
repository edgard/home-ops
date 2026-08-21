package main

import rego.v1

deny contains msg if {
  input.kind == "HTTPRoute"
  some hostname in object.get(input.spec, "hostnames", [])
  not endswith(hostname, ".edgard.org")
  msg := sprintf("HTTPRoute/%s hostname %s must end with .edgard.org", [input.metadata.name, hostname])
}

deny contains msg if {
  input.kind == "HTTPRoute"
  not has_expected_gateway_parent_ref
  msg := sprintf("HTTPRoute/%s must target gateway/platform-system section https", [input.metadata.name])
}

has_expected_gateway_parent_ref if {
  some ref in object.get(input.spec, "parentRefs", [])
  object.get(ref, "name", "") == "gateway"
  object.get(ref, "namespace", "") == "platform-system"
  object.get(ref, "sectionName", "") == "https"
}

deny contains msg if {
  annotations := object.get(input.metadata, "annotations", {})
  some annotation in object.keys(annotations)
  startswith(annotation, "external-dns.alpha.kubernetes.io/")
  msg := sprintf("%s/%s uses retired ExternalDNS annotation %s", [input.kind, input.metadata.name, annotation])
}

deny contains msg if {
  input.kind == "Gateway"
  input.metadata.name == "gateway"
  object.get(input.metadata, "namespace", "") == "platform-system"
  annotations := object.get(input.metadata, "annotations", {})
  object.get(annotations, "external-dns.kubernetes.io/target", "") != "192.168.1.241"
  msg := "Gateway/gateway must set external-dns.kubernetes.io/target to 192.168.1.241"
}
