package main

import rego.v1

valid_app := {
  "path": "/repo/apps/selfhosted/demo",
  "category": "selfhosted",
  "app_name": "demo",
  "generated_name": "selfhosted-demo",
  "app_file": "/repo/apps/selfhosted/demo/app.yaml",
  "values_file": "/repo/apps/selfhosted/demo/values.yaml",
  "has_app_file": true,
  "has_values_file": true,
  "has_nonempty_values_file": true,
  "chart_repo": "oci://ghcr.io/example/app-template",
  "chart_version": "1.2.3",
  "chart_name": "",
  "sync_wave": "0",
  "has_ignore_differences": false,
  "ignore_differences_type": "",
  "ignore_differences": [],
}

test_valid_metadata_passes if {
  results := deny with input as {"apps": [valid_app]}
  count(results) == 0
}

test_missing_metadata_file_denied if {
  app := object.union(valid_app, {"has_app_file": false})
  "Missing metadata file: /repo/apps/selfhosted/demo/app.yaml" in deny with input as {"apps": [app]}
}

test_missing_values_file_denied if {
  app := object.union(valid_app, {"has_values_file": false, "has_nonempty_values_file": false})
  "Missing values file: /repo/apps/selfhosted/demo/values.yaml" in deny with input as {"apps": [app]}
}

test_empty_values_file_denied if {
  app := object.union(valid_app, {"has_nonempty_values_file": false})
  "Values file must not be empty: /repo/apps/selfhosted/demo/values.yaml" in deny with input as {"apps": [app]}
}

test_missing_chart_repo_denied if {
  app := object.union(valid_app, {"chart_repo": ""})
  "Missing chart.repo in /repo/apps/selfhosted/demo/app.yaml" in deny with input as {"apps": [app]}
}

test_missing_chart_version_denied if {
  app := object.union(valid_app, {"chart_version": ""})
  "Missing chart.version in /repo/apps/selfhosted/demo/app.yaml" in deny with input as {"apps": [app]}
}

test_missing_chart_name_for_non_oci_repo_denied if {
  app := object.union(valid_app, {
    "chart_repo": "https://charts.example.com",
    "chart_name": "",
  })
  "Missing chart.name for non-OCI chart repo in /repo/apps/selfhosted/demo/app.yaml" in deny with input as {"apps": [app]}
}

test_invalid_sync_wave_denied if {
  app := object.union(valid_app, {"sync_wave": "invalid"})
  "sync.wave must be one of -4, -3, -2, -1, 0 in /repo/apps/selfhosted/demo/app.yaml" in deny with input as {"apps": [app]}
}

test_missing_sync_wave_denied if {
  app := object.union(valid_app, {"sync_wave": ""})
  "Missing sync.wave in /repo/apps/selfhosted/demo/app.yaml" in deny with input as {"apps": [app]}
}

test_ignore_differences_must_be_list if {
  app := object.union(valid_app, {
    "has_ignore_differences": true,
    "ignore_differences_type": "!!map",
  })
  "ignoreDifferences must be a list in /repo/apps/selfhosted/demo/app.yaml" in deny with input as {"apps": [app]}
}

test_ignore_differences_item_requires_group if {
  app := object.union(valid_app, {
    "has_ignore_differences": true,
    "ignore_differences_type": "!!seq",
    "ignore_differences": [{"index": 0, "has_group": false, "has_kind": true}],
  })
  "ignoreDifferences[0] must define both group and kind in /repo/apps/selfhosted/demo/app.yaml" in deny with input as {"apps": [app]}
}

test_ignore_differences_item_requires_kind if {
  app := object.union(valid_app, {
    "has_ignore_differences": true,
    "ignore_differences_type": "!!seq",
    "ignore_differences": [{"index": 0, "has_group": true, "has_kind": false}],
  })
  "ignoreDifferences[0] must define both group and kind in /repo/apps/selfhosted/demo/app.yaml" in deny with input as {"apps": [app]}
}
