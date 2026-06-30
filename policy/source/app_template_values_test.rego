package main

import rego.v1

test_valid_app_template_values_pass if {
  results := deny with input as {"apps": [valid_app_template], "manifests": [valid_manifest, valid_root_manifest]}
  count(results) == 0
}

test_requires_main_primary_controller if {
  app := object.union(valid_app_template, {
    "controller_keys": ["demo"],
  })
  "app-template values must use controllers.main as the canonical primary controller in /repo/apps/selfhosted/demo/values.yaml" in deny with input as {"apps": [app], "manifests": [valid_manifest]}
}

test_allows_routed_apps_without_dashboard_annotations if {
  app := object.union(valid_app_template, {
    "route_main_annotations": {},
  })
  results := deny with input as {"apps": [app], "manifests": [valid_manifest]}
  count(results) == 0
}
