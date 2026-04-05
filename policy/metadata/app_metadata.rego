package main

import rego.v1

allowed_sync_waves := {"-4", "-3", "-2", "-1", "0"}

deny contains msg if {
  some app in input.apps
  not app.has_app_file
  msg := sprintf("Missing metadata file: %s", [app.app_file])
}

deny contains msg if {
  some app in input.apps
  not app.has_values_file
  msg := sprintf("Missing values file: %s", [app.values_file])
}

deny contains msg if {
  some app in input.apps
  app.has_values_file
  not app.has_nonempty_values_file
  msg := sprintf("Values file must not be empty: %s", [app.values_file])
}

deny contains msg if {
  some app in input.apps
  app.has_app_file
  app.chart_repo == ""
  msg := sprintf("Missing chart.repo in %s", [app.app_file])
}

deny contains msg if {
  some app in input.apps
  app.has_app_file
  app.chart_version == ""
  msg := sprintf("Missing chart.version in %s", [app.app_file])
}

deny contains msg if {
  some app in input.apps
  app.has_app_file
  app.chart_repo != ""
  not startswith(app.chart_repo, "oci://")
  app.chart_name == ""
  msg := sprintf("Missing chart.name for non-OCI chart repo in %s", [app.app_file])
}

deny contains msg if {
  some app in input.apps
  app.has_app_file
  app.sync_wave == ""
  msg := sprintf("Missing sync.wave in %s", [app.app_file])
}

deny contains msg if {
  some app in input.apps
  app.has_app_file
  app.sync_wave != ""
  not allowed_sync_waves[app.sync_wave]
  msg := sprintf("sync.wave must be one of -4, -3, -2, -1, 0 in %s", [app.app_file])
}

deny contains msg if {
  some app in input.apps
  app.has_app_file
  app.has_ignore_differences
  app.ignore_differences_type != "!!seq"
  msg := sprintf("ignoreDifferences must be a list in %s", [app.app_file])
}

deny contains msg if {
  some app in input.apps
  app.has_app_file
  app.has_ignore_differences
  app.ignore_differences_type == "!!seq"
  some item in app.ignore_differences
  not item.has_group
  msg := sprintf("ignoreDifferences[%d] must define both group and kind in %s", [item.index, app.app_file])
}

deny contains msg if {
  some app in input.apps
  app.has_app_file
  app.has_ignore_differences
  app.ignore_differences_type == "!!seq"
  some item in app.ignore_differences
  not item.has_kind
  msg := sprintf("ignoreDifferences[%d] must define both group and kind in %s", [item.index, app.app_file])
}

deny contains msg if {
  some i, j
  i < j
  first := input.apps[i]
  second := input.apps[j]
  first.generated_name == second.generated_name
  msg := sprintf("Duplicate generated application name '%s': %s and %s", [first.generated_name, first.path, second.path])
}
