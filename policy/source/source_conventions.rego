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

vendored_manifest_exemptions := {
  "apps/platform-system/gateway-api/manifests/gateway-api-crds.yaml",
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
  list_contains(object.get(app, "service_main_ports", []), "http")
  object.get(object.get(app, "service_main_annotations", {}), "gatus.edgard.org/enabled", "") != "true"
  msg := sprintf("service.main must enable gatus.edgard.org/enabled for routed HTTP apps in %s", [app.values_file])
}

deny contains msg if {
  some app in input.apps
  is_argocd_chart(app)
  count(object.get(app, "raw_httproute_manifest_paths", [])) > 0
  msg := sprintf("argo-cd chart apps must declare HTTPRoute via values.yaml server.httproute instead of a raw manifest in %s", [app.values_file])
}

deny contains msg if {
  some manifest in input.manifests
  not is_vendored_manifest(manifest)
  not has_expected_manifest_filename(manifest)
  msg := sprintf("owned manifest filename must start with the owning app or resource name in %s", [manifest.path])
}

deny contains msg if {
  some manifest in input.manifests
  not is_vendored_manifest(manifest)
  not has_expected_manifest_top_level_order(manifest)
  msg := sprintf("owned manifest must order fields as apiVersion, kind, metadata, spec in %s", [manifest.path])
}

deny contains msg if {
  some manifest in input.manifests
  not is_vendored_manifest(manifest)
  not has_expected_metadata_order(manifest)
  msg := sprintf("metadata keys must order fields as name, namespace, labels, annotations in %s", [manifest.path])
}

is_app_template_v4(app) if {
  app.chart_repo == "oci://ghcr.io/bjw-s-labs/helm/app-template"
  app.chart_version == "4.6.2"
}

is_argocd_chart(app) if {
  app.chart_repo == "oci://ghcr.io/argoproj/argo-helm/argo-cd"
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

is_vendored_manifest(manifest) if {
  vendored_manifest_exemptions[manifest.relative_path]
}

has_expected_manifest_filename(manifest) if {
  startswith(manifest.relative_path, "apps/")
  startswith(manifest.basename, sprintf("%s-", [manifest_owner_name(manifest)]))
}

has_expected_manifest_filename(manifest) if {
  not startswith(manifest.relative_path, "apps/")
  startswith(manifest.basename, sprintf("%s.", [manifest_owner_name(manifest)]))
}

manifest_owner_name(manifest) := app_name if {
  startswith(manifest.relative_path, "apps/")
  parts := split(manifest.relative_path, "/")
  count(parts) >= 5
  app_name := parts[2]
}

manifest_owner_name(manifest) := basename_prefix if {
  not startswith(manifest.relative_path, "apps/")
  basename_parts := split(manifest.basename, ".")
  basename_prefix := basename_parts[0]
}

has_expected_manifest_top_level_order(manifest) if {
  keys := object.get(manifest, "top_level_keys", [])
  count(keys) >= 3
  keys[0] == "apiVersion"
  keys[1] == "kind"
  keys[2] == "metadata"
  spec_order_is_valid(keys)
}

spec_order_is_valid(keys) if {
  not list_contains(keys, "spec")
}

spec_order_is_valid(keys) if {
  list_contains(keys, "spec")
  count(keys) >= 4
  keys[3] == "spec"
}

has_expected_metadata_order(manifest) if {
  keys := object.get(manifest, "metadata_keys", [])
  ordered_if_present(keys, "name", "namespace")
  ordered_if_present(keys, "name", "labels")
  ordered_if_present(keys, "name", "annotations")
  ordered_if_present(keys, "namespace", "labels")
  ordered_if_present(keys, "namespace", "annotations")
  ordered_if_present(keys, "labels", "annotations")
}

order_position(keys, key) := pos if {
  some i
  keys[i] == key
  pos := i
}

order_position(keys, key) := 999 if {
  not list_contains(keys, key)
}

list_contains(keys, key) if {
  some i
  keys[i] == key
}

ordered_if_present(keys, first, second) if {
  not list_contains(keys, first)
}

ordered_if_present(keys, first, second) if {
  not list_contains(keys, second)
}

ordered_if_present(keys, first, second) if {
  list_contains(keys, first)
  list_contains(keys, second)
  order_position(keys, first) <= order_position(keys, second)
}
