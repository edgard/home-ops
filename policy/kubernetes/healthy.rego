package main

import rego.v1

allowed_storage_classes := {"nfs-fast", "nfs-media", "nfs-restic"}

root_run_image_prefixes := [
  "ghcr.io/home-assistant/home-assistant:",
  "ghcr.io/koush/scrypted:",
  "ghcr.io/karakeep-app/karakeep:",
  "ghcr.io/paperless-ngx/paperless-ngx:",
  "icereed/paperless-gpt:",
  "qmcgaw/gluetun:",
  "restic/rest-server:",
  "restic/restic:",
  "ghcr.io/tailscale/tailscale:",
  "lscr.io/linuxserver/",
  "plexinc/pms-docker:",
]

security_context_exempt_image_prefixes := [
  "docker.io/apache/tika:",
  "docker.io/gotenberg/gotenberg:",
  "docker.io/library/redis:",
  "ghcr.io/home-assistant/home-assistant:",
  "ghcr.io/koush/scrypted:",
  "ghcr.io/paperless-ngx/paperless-ngx:",
  "icereed/paperless-gpt:",
  "qmcgaw/gluetun:",
  "restic/rest-server:",
  "restic/restic:",
  "ghcr.io/tailscale/tailscale:",
]

deny contains msg if {
  is_app_template_workload
  object.get(input.spec, "replicas", 1) != 1
  msg := sprintf("%s/%s must set replicas to 1", [input.kind, input.metadata.name])
}

deny contains msg if {
  is_app_template_deployment
  object.get(object.get(input.spec, "strategy", {}), "type", "") != "Recreate"
  msg := sprintf("Deployment/%s must use Recreate strategy", [input.metadata.name])
}

deny contains msg if {
  is_app_template_workload
  some container in workload_containers
  not exempt_security_context(container)
  object.get(object.get(container, "securityContext", {}), "allowPrivilegeEscalation", false)
  msg := sprintf("%s/%s container %s must set allowPrivilegeEscalation to false", [input.kind, input.metadata.name, container.name])
}

deny contains msg if {
  is_app_template_workload
  some container in workload_containers
  not exempt_security_context(container)
  not drops_all_capabilities(container)
  msg := sprintf("%s/%s container %s must drop ALL capabilities", [input.kind, input.metadata.name, container.name])
}

deny contains msg if {
  is_app_template_workload
  some container in workload_containers
  not exempt_root_run(container)
  not effective_run_as_non_root(container)
  msg := sprintf("%s/%s container %s must run as non-root", [input.kind, input.metadata.name, container.name])
}

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
  input.kind == "ExternalSecret"
  object.get(object.get(input.spec, "secretStoreRef", {}), "name", "") != "external-secrets-store"
  msg := sprintf("ExternalSecret/%s must use secretStoreRef.name external-secrets-store", [input.metadata.name])
}

deny contains msg if {
  input.kind == "PersistentVolumeClaim"
  storage_class := object.get(input.spec, "storageClassName", "")
  storage_class != ""
  not allowed_storage_classes[storage_class]
  msg := sprintf("PersistentVolumeClaim/%s must use an approved storageClassName", [input.metadata.name])
}

deny contains msg if {
  some image in pod_images
  lower(image) == sprintf("%s:latest", [trim_suffix(image, ":latest")])
  msg := sprintf("%s/%s must not use latest image tags", [input.kind, input.metadata.name])
}

is_app_template_workload if {
  input.kind in {"Deployment", "StatefulSet"}
  startswith(object.get(object.get(input.metadata, "labels", {}), "helm.sh/chart", ""), "app-template-")
}

is_app_template_deployment if {
  input.kind == "Deployment"
  startswith(object.get(object.get(input.metadata, "labels", {}), "helm.sh/chart", ""), "app-template-")
}

workload_containers contains container if {
  some container in object.get(object.get(object.get(input.spec, "template", {}), "spec", {}), "containers", [])
}

workload_containers contains container if {
  some container in object.get(object.get(object.get(input.spec, "template", {}), "spec", {}), "initContainers", [])
}

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

effective_run_as_non_root(container) if {
  object.get(object.get(container, "securityContext", {}), "runAsNonRoot", false)
}

effective_run_as_non_root(container) if {
  object.get(object.get(container, "securityContext", {}), "runAsNonRoot", "missing") == "missing"
  object.get(object.get(object.get(object.get(input.spec, "template", {}), "spec", {}), "securityContext", {}), "runAsNonRoot", false)
}

drops_all_capabilities(container) if {
  "ALL" in object.get(object.get(object.get(container, "securityContext", {}), "capabilities", {}), "drop", [])
}

exempt_root_run(container) if {
  image_matches_prefix(object.get(container, "image", ""), root_run_image_prefixes)
}

exempt_security_context(container) if {
  image_matches_prefix(object.get(container, "image", ""), security_context_exempt_image_prefixes)
}

image_matches_prefix(image, prefixes) if {
  some prefix in prefixes
  startswith(image, prefix)
}

has_expected_gateway_parent_ref if {
  some ref in object.get(input.spec, "parentRefs", [])
  object.get(ref, "name", "") == "gateway"
  object.get(ref, "namespace", "") == "platform-system"
  object.get(ref, "sectionName", "") == "https"
}
