package main

import rego.v1

allowed_app_template_values_orders := {
  "controllers",
  "controllers,configMaps",
  "defaultPodOptions,controllers,persistence",
  "defaultPodOptions,controllers,route",
  "defaultPodOptions,controllers,route,persistence",
  "defaultPodOptions,controllers,service",
  "defaultPodOptions,controllers,service,persistence",
  "defaultPodOptions,controllers,service,route",
  "defaultPodOptions,controllers,service,route,persistence",
  "defaultPodOptions,controllers,service,route,persistence,configMaps",
  "defaultPodOptions,controllers,serviceAccount,rbac,service",
  "defaultPodOptions,controllers,serviceAccount,rbac,service,persistence",
  "defaultPodOptions,controllers,serviceAccount,rbac,service,route",
  "defaultPodOptions,controllers,serviceAccount,rbac,service,route,persistence",
  "defaultPodOptions,controllers,serviceAccount,rbac,service,route,persistence,configMaps",
}

deny contains msg if {
  some app in input.apps
  is_app_template_v4(app)
  not allowed_app_template_values_orders[concat(",", object.get(app, "values_top_level_keys", []))]
  msg := sprintf("app-template values must use the canonical top-level section order in %s", [app.values_file])
}

deny contains msg if {
  some app in input.apps
  is_app_template_v4(app)
  has_default_pod_options(app)
  not is_canonical_non_root_profile(app)
  not is_canonical_root_profile(app)
  msg := sprintf("defaultPodOptions.securityContext must use either the canonical non-root profile or the explicit root-required profile in %s", [app.values_file])
}

deny contains msg if {
  some app in input.apps
  is_app_template_v4(app)
  count(object.get(app, "controller_keys", [])) == 1
  app.controller_keys[0] != "main"
  msg := sprintf("app-template values must use controllers.main as the canonical primary controller in %s", [app.values_file])
}

deny contains msg if {
  some app in input.apps
  is_app_template_v4(app)
  count(object.get(app, "controller_keys", [])) > 1
  not list_contains(object.get(app, "controller_keys", []), "main")
  msg := sprintf("multi-controller app-template values must expose the primary controller as controllers.main in %s", [app.values_file])
}

deny contains msg if {
  some app in input.apps
  is_app_template_v4(app)
  count(object.get(app, "service_keys", [])) > 0
  not list_contains(object.get(app, "service_keys", []), "main")
  msg := sprintf("app-template values with services must expose the primary service as service.main in %s", [app.values_file])
}

deny contains msg if {
  some app in input.apps
  is_app_template_v4(app)
  app.service_main_controller != ""
  app.service_main_controller != "main"
  msg := sprintf("service.main.controller must target main in %s", [app.values_file])
}

deny contains msg if {
  some app in input.apps
  is_app_template_v4(app)
  count(object.get(app, "route_keys", [])) > 0
  not list_contains(object.get(app, "route_keys", []), "main")
  msg := sprintf("app-template values with routes must expose the primary route as route.main in %s", [app.values_file])
}

deny contains msg if {
  some app in input.apps
  is_app_template_v4(app)
  some identifier in object.get(app, "route_main_backend_identifiers", [])
  identifier != ""
  identifier != "main"
  msg := sprintf("route.main backendRefs must target identifier main in %s", [app.values_file])
}

deny contains msg if {
  some app in input.apps
  is_app_template_v4(app)
  some hostname in object.get(app, "route_main_hostnames", [])
  hostname != ""
  not endswith(hostname, ".edgard.org")
  msg := sprintf("route.main hostnames must stay within *.edgard.org in %s", [app.values_file])
}

deny contains msg if {
  some app in input.apps
  is_app_template_v4(app)
  count(object.get(app, "route_main_hostnames", [])) > 0
  object.get(object.get(app, "route_main_annotations", {}), "gethomepage.dev/enabled", "") != "true"
  msg := sprintf("route.main must define the full gethomepage.dev annotation set in %s", [app.values_file])
}

deny contains msg if {
  some app in input.apps
  is_app_template_v4(app)
  count(object.get(app, "route_main_hostnames", [])) > 0
  object.get(object.get(app, "route_main_annotations", {}), "gethomepage.dev/name", "") == ""
  msg := sprintf("route.main must define the full gethomepage.dev annotation set in %s", [app.values_file])
}

deny contains msg if {
  some app in input.apps
  is_app_template_v4(app)
  count(object.get(app, "route_main_hostnames", [])) > 0
  object.get(object.get(app, "route_main_annotations", {}), "gethomepage.dev/group", "") == ""
  msg := sprintf("route.main must define the full gethomepage.dev annotation set in %s", [app.values_file])
}

deny contains msg if {
  some app in input.apps
  is_app_template_v4(app)
  count(object.get(app, "route_main_hostnames", [])) > 0
  object.get(object.get(app, "route_main_annotations", {}), "gethomepage.dev/icon", "") == ""
  msg := sprintf("route.main must define the full gethomepage.dev annotation set in %s", [app.values_file])
}

deny contains msg if {
  some app in input.apps
  is_app_template_v4(app)
  count(object.get(app, "route_main_hostnames", [])) > 0
  object.get(object.get(app, "route_main_annotations", {}), "gethomepage.dev/app", "") == ""
  msg := sprintf("route.main must define the full gethomepage.dev annotation set in %s", [app.values_file])
}

deny contains msg if {
  some app in input.apps
  is_app_template_v4(app)
  count(object.get(app, "route_main_hostnames", [])) > 0
  object.get(object.get(app, "route_main_annotations", {}), "gatus.home-operations.com/endpoint", "") == ""
  msg := sprintf("route.main must define gatus.home-operations.com/endpoint for routed apps in %s", [app.values_file])
}

deny contains msg if {
  some app in input.apps
  is_app_template_chart(app)
  some pvc in object.get(app, "local_persistent_volume_claims", [])
  object.get(pvc, "backup_annotation", "") != "true"
  msg := sprintf("local persistentVolumeClaim %s must set k8up.io/backup: \"true\" in %s", [pvc.name, app.values_file])
}

deny contains msg if {
  some app in input.apps
  is_app_template_chart(app)
  some claim in object.get(app, "existing_claim_persistence", [])
  object.get(claim, "backup_annotation", "") != ""
  msg := sprintf("existingClaim persistence %s must not set k8up.io/backup in %s", [claim.name, app.values_file])
}

deny contains msg if {
  some app in input.apps
  is_app_template_chart(app)
  count(object.get(app, "local_persistent_volume_claims", [])) > 0
  object.get(app, "has_name_override", false)
  msg := sprintf("K8up-backed app-template values must not set nameOverride in %s", [app.values_file])
}

deny contains msg if {
  some app in input.apps
  is_app_template_chart(app)
  count(object.get(app, "local_persistent_volume_claims", [])) > 0
  object.get(app, "has_fullname_override", false)
  msg := sprintf("K8up-backed app-template values must not set fullnameOverride in %s", [app.values_file])
}

is_app_template_chart(app) if {
  app.chart_repo == "oci://ghcr.io/bjw-s-labs/helm/app-template"
}

is_app_template_v4(app) if {
  app.chart_repo == "oci://ghcr.io/bjw-s-labs/helm/app-template"
  app.chart_version == "4.6.2"
}

has_default_pod_options(app) if {
  sc := object.get(app, "default_pod_security_context", {})
  some key in object.keys(sc)
  object.get(sc, key, "") != ""
}

is_canonical_non_root_profile(app) if {
  sc := object.get(app, "default_pod_security_context", {})
  object.get(sc, "fsGroup", "") == "1000"
  object.get(sc, "fsGroupChangePolicy", "") == "OnRootMismatch"
  object.get(sc, "runAsGroup", "") == "1000"
  object.get(sc, "runAsNonRoot", "") == "true"
  object.get(sc, "runAsUser", "") == "1000"
}

is_canonical_root_profile(app) if {
  sc := object.get(app, "default_pod_security_context", {})
  object.get(sc, "fsGroup", "") == "0"
  object.get(sc, "fsGroupChangePolicy", "") == "OnRootMismatch"
  object.get(sc, "runAsGroup", "") == "0"
  object.get(sc, "runAsNonRoot", "") == "false"
  object.get(sc, "runAsUser", "") == "0"
}
