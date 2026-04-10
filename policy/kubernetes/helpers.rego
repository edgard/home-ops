package main

import rego.v1

pod_images contains image if {
  spec := pod_spec
  some container in object.get(spec, "containers", [])
  image := object.get(container, "image", "")
  image != ""
}

pod_images contains image if {
  spec := pod_spec
  some container in object.get(spec, "initContainers", [])
  image := object.get(container, "image", "")
  image != ""
}

pod_spec := object.get(input, "spec", {}) if {
  input.kind == "Pod"
}

pod_spec := object.get(object.get(input.spec, "template", {}), "spec", {}) if {
  input.kind in {"Deployment", "StatefulSet", "DaemonSet", "Job"}
}

pod_spec := object.get(object.get(object.get(input.spec, "jobTemplate", {}), "spec", {}), "template", {}).spec if {
  input.kind == "CronJob"
}
