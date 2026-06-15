package main

import rego.v1

allowed_sync_waves := {"-4", "-3", "-2", "-1", "0"}
allowed_dr_tiers := {"critical", "standard", "platform", "media", "disposable"}
allowed_dr_restore_modes := {"restic-appdata", "gitops", "external", "none"}

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
  app.dr_tier == ""
  msg := sprintf("Missing dr.tier in %s", [app.app_file])
}

deny contains msg if {
  some app in input.apps
  app.has_app_file
  app.dr_tier != ""
  not allowed_dr_tiers[app.dr_tier]
  msg := sprintf("dr.tier must be one of critical, standard, platform, media, disposable in %s", [app.app_file])
}

deny contains msg if {
  some app in input.apps
  app.has_app_file
  app.dr_restore_mode == ""
  msg := sprintf("Missing dr.restore.mode in %s", [app.app_file])
}

deny contains msg if {
  some app in input.apps
  app.has_app_file
  app.dr_restore_mode != ""
  not allowed_dr_restore_modes[app.dr_restore_mode]
  msg := sprintf("dr.restore.mode must be one of restic-appdata, gitops, external, none in %s", [app.app_file])
}

deny contains msg if {
  some app in input.apps
  app.has_app_file
  app.has_dr_restore_paths
  msg := sprintf("dr.restore.paths must not be set in %s; restic-appdata paths are derived from namespace and PVC name", [app.app_file])
}

deny contains msg if {
  some app in input.apps
  app.has_app_file
  app.dr_restore_mode == "restic-appdata"
  app.local_persistent_volume_claim_count != 1
  msg := sprintf("restic-appdata apps must define exactly one local non-existingClaim PVC in %s", [app.values_file])
}

deny contains msg if {
  some app in input.apps
  app.has_app_file
  app.dr_restore_mode == "restic-appdata"
  app.has_name_override
  msg := sprintf("restic-appdata apps must not set nameOverride or fullnameOverride in %s", [app.values_file])
}

deny contains msg if {
  some app in input.apps
  app.has_app_file
  app.dr_restore_mode == "restic-appdata"
  app.has_fullname_override
  msg := sprintf("restic-appdata apps must not set nameOverride or fullnameOverride in %s", [app.values_file])
}

deny contains msg if {
  some app in input.apps
  app.has_app_file
  app.dr_tier == "critical"
  app.dr_restore_mode == "none"
  msg := sprintf("critical apps must not use dr.restore.mode none in %s", [app.app_file])
}

deny contains msg if {
  some app in input.apps
  app.has_app_file
  app.local_persistent_volume_claim_count > 0
  app.dr_tier != "disposable"
  app.dr_restore_mode != "restic-appdata"
  msg := sprintf("apps with local PVCs must use dr.restore.mode restic-appdata unless dr.tier is disposable in %s", [app.app_file])
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

deny contains msg if {
  some i, j
  i < j
  first := input.apps[i]
  second := input.apps[j]
  first.app_name == second.app_name
  msg := sprintf("Duplicate Argo CD application name '%s': %s and %s", [first.app_name, first.path, second.path])
}
