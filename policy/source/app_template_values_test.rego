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

test_requires_gatus_for_routed_http_apps if {
  app := object.union(valid_app_template, {
    "service_main_annotations": {
      "gatus.edgard.org/enabled": "",
    },
  })
  "service.main must enable gatus.edgard.org/enabled for routed HTTP apps in /repo/apps/selfhosted/demo/values.yaml" in deny with input as {"apps": [app], "manifests": [valid_manifest]}
}

test_requires_complete_homepage_annotations if {
  app := object.union(valid_app_template, {
    "route_main_annotations": {
      "gethomepage.dev/enabled": "true",
      "gethomepage.dev/name": "Demo",
      "gethomepage.dev/group": "Selfhosted",
      "gethomepage.dev/icon": "",
      "gethomepage.dev/app": "demo",
    },
  })
  "route.main must define the full gethomepage.dev annotation set in /repo/apps/selfhosted/demo/values.yaml" in deny with input as {"apps": [app], "manifests": [valid_manifest]}
}
