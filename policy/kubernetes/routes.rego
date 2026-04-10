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

deny contains msg if {
  input.kind == "HTTPRoute"
  object.get(object.get(input.metadata, "annotations", {}), "gethomepage.dev/enabled", "") == "true"
  object.get(object.get(input.metadata, "annotations", {}), "gethomepage.dev/group", "") == ""
  msg := sprintf("HTTPRoute/%s must define gethomepage.dev/group when homepage annotations are enabled", [input.metadata.name])
}

deny contains msg if {
  input.kind == "HTTPRoute"
  object.get(object.get(input.metadata, "annotations", {}), "gethomepage.dev/enabled", "") == "true"
  object.get(object.get(input.metadata, "annotations", {}), "gethomepage.dev/icon", "") == ""
  msg := sprintf("HTTPRoute/%s must define gethomepage.dev/icon when homepage annotations are enabled", [input.metadata.name])
}

deny contains msg if {
  input.kind == "HTTPRoute"
  object.get(object.get(input.metadata, "annotations", {}), "gethomepage.dev/enabled", "") == "true"
  object.get(object.get(input.metadata, "annotations", {}), "gethomepage.dev/app", "") == ""
  msg := sprintf("HTTPRoute/%s must define gethomepage.dev/app when homepage annotations are enabled", [input.metadata.name])
}

deny contains msg if {
  input.kind == "HTTPRoute"
  object.get(object.get(input.metadata, "annotations", {}), "gethomepage.dev/enabled", "") == "true"
  object.get(object.get(input.metadata, "annotations", {}), "gethomepage.dev/name", "") == ""
  msg := sprintf("HTTPRoute/%s must define gethomepage.dev/name when homepage annotations are enabled", [input.metadata.name])
}

has_expected_gateway_parent_ref if {
  some ref in object.get(input.spec, "parentRefs", [])
  object.get(ref, "name", "") == "gateway"
  object.get(ref, "namespace", "") == "platform-system"
  object.get(ref, "sectionName", "") == "https"
}
