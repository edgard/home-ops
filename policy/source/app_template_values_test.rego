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

test_rejects_invalid_controllers_across_supported_majors if {
  every version in ["4.6.2", "5.1.0", "5.2.0"] {
    app := object.union(valid_app_template, {"chart_version": version, "controller_keys": ["demo"]})
    results := deny with input as {"apps": [app]}
    count(results) > 0
  }
}

test_accepts_supported_chart_versions if {
  every version in ["4.6.2", "5.1.0", "5.2.0"] {
    app := object.union(valid_app_template, {"chart_version": version})
    results := deny with input as {"apps": [app]}
    count(results) == 0
  }
}

test_rejects_unsupported_or_malformed_chart_versions if {
  every version in ["3.7.0", "6.0.0", "", "latest", "5.invalid"] {
    app := object.union(valid_app_template, {"chart_version": version})
    results := deny with input as {"apps": [app]}
    count(results) > 0
  }
}
