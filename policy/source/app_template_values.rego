package main

import rego.v1

app_template_section_order := [
  "defaultPodOptions",
  "controllers",
  "serviceAccount",
  "rbac",
  "service",
  "route",
  "persistence",
  "configMaps",
]

deny contains msg if {
  some app in input.apps
  is_supported_app_template(app)
  not has_canonical_section_order(object.get(app, "values_top_level_keys", []))
  msg := sprintf("app-template values must use the canonical top-level section order in %s", [app.values_file])
}

has_canonical_section_order(keys) if {
  every i, first in app_template_section_order {
    every j, second in app_template_section_order {
      section_pair_ordered(keys, i, j, first, second)
    }
  }
}

section_pair_ordered(keys, i, j, _, _) if {
  i >= j
}

section_pair_ordered(keys, _, _, first, second) if {
  ordered_if_present(keys, first, second)
}

ordered_if_present(keys, first, second) if {
  not first in keys
}

ordered_if_present(keys, first, second) if {
  not second in keys
}

ordered_if_present(keys, first, second) if {
  indexof(keys, first) < indexof(keys, second)
}

deny contains msg if {
  some app in input.apps
  is_supported_app_template(app)
  has_default_pod_options(app)
  not is_canonical_non_root_profile(app)
  not is_canonical_root_profile(app)
  msg := sprintf("defaultPodOptions.securityContext must use either the canonical non-root profile or the explicit root-required profile in %s", [app.values_file])
}

deny contains msg if {
  some app in input.apps
  is_supported_app_template(app)
  count(object.get(app, "controller_keys", [])) == 1
  app.controller_keys[0] != "main"
  msg := sprintf("app-template values must use controllers.main as the canonical primary controller in %s", [app.values_file])
}

deny contains msg if {
  some app in input.apps
  is_supported_app_template(app)
  count(object.get(app, "controller_keys", [])) > 1
  not list_contains(object.get(app, "controller_keys", []), "main")
  msg := sprintf("multi-controller app-template values must expose the primary controller as controllers.main in %s", [app.values_file])
}

deny contains msg if {
  some app in input.apps
  is_supported_app_template(app)
  count(object.get(app, "service_keys", [])) > 0
  not list_contains(object.get(app, "service_keys", []), "main")
  msg := sprintf("app-template values with services must expose the primary service as service.main in %s", [app.values_file])
}

deny contains msg if {
  some app in input.apps
  is_supported_app_template(app)
  app.service_main_controller != ""
  app.service_main_controller != "main"
  msg := sprintf("service.main.controller must target main in %s", [app.values_file])
}

deny contains msg if {
  some app in input.apps
  is_supported_app_template(app)
  count(object.get(app, "route_keys", [])) > 0
  not list_contains(object.get(app, "route_keys", []), "main")
  msg := sprintf("app-template values with routes must expose the primary route as route.main in %s", [app.values_file])
}

deny contains msg if {
  some app in input.apps
  is_supported_app_template(app)
  some identifier in object.get(app, "route_main_backend_identifiers", [])
  identifier != ""
  identifier != "main"
  msg := sprintf("route.main backendRefs must target identifier main in %s", [app.values_file])
}

deny contains msg if {
  some app in input.apps
  is_supported_app_template(app)
  some hostname in object.get(app, "route_main_hostnames", [])
  hostname != ""
  not endswith(hostname, ".edgard.org")
  msg := sprintf("route.main hostnames must stay within *.edgard.org in %s", [app.values_file])
}

is_supported_app_template(app) if {
  app.chart_repo == "oci://ghcr.io/bjw-s-labs/helm/app-template"
  regex.match(`^[45]\.[0-9]+\.[0-9]+$`, app.chart_version)
}

deny contains msg if {
  some app in input.apps
  app.chart_repo == "oci://ghcr.io/bjw-s-labs/helm/app-template"
  not is_supported_app_template(app)
  msg := sprintf("unsupported app-template chart version %s in %s; review source policy compatibility", [app.chart_version, app.values_file])
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
