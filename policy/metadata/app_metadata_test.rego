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
  "dr_tier": "standard",
  "dr_restore_mode": "restic-appdata",
  "has_dr_restore_paths": false,
  "has_name_override": false,
  "has_fullname_override": false,
  "local_persistent_volume_claim_count": 1,
  "has_existing_claim": false,
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

test_missing_dr_tier_denied if {
  app := object.union(valid_app, {"dr_tier": ""})
  "Missing dr.tier in /repo/apps/selfhosted/demo/app.yaml" in deny with input as {"apps": [app]}
}

test_invalid_dr_tier_denied if {
  app := object.union(valid_app, {"dr_tier": "gold"})
  "dr.tier must be one of critical, standard, platform, media, disposable in /repo/apps/selfhosted/demo/app.yaml" in deny with input as {"apps": [app]}
}

test_missing_dr_restore_mode_denied if {
  app := object.union(valid_app, {"dr_restore_mode": ""})
  "Missing dr.restore.mode in /repo/apps/selfhosted/demo/app.yaml" in deny with input as {"apps": [app]}
}

test_invalid_dr_restore_mode_denied if {
  app := object.union(valid_app, {"dr_restore_mode": "snapshot"})
  "dr.restore.mode must be one of restic-appdata, gitops, external, none in /repo/apps/selfhosted/demo/app.yaml" in deny with input as {"apps": [app]}
}

test_dr_restore_paths_are_rejected if {
  app := object.union(valid_app, {"has_dr_restore_paths": true})
  "dr.restore.paths must not be set in /repo/apps/selfhosted/demo/app.yaml; restic-appdata paths are derived from namespace and PVC name" in deny with input as {"apps": [app]}
}

test_restic_appdata_requires_one_local_pvc if {
  app := object.union(valid_app, {"local_persistent_volume_claim_count": 0})
  "restic-appdata apps must define exactly one local non-existingClaim PVC in /repo/apps/selfhosted/demo/values.yaml" in deny with input as {"apps": [app]}
}

test_restic_appdata_rejects_multiple_local_pvcs if {
  app := object.union(valid_app, {"local_persistent_volume_claim_count": 2})
  "restic-appdata apps must define exactly one local non-existingClaim PVC in /repo/apps/selfhosted/demo/values.yaml" in deny with input as {"apps": [app]}
}

test_restic_appdata_rejects_name_override if {
  app := object.union(valid_app, {"has_name_override": true})
  "restic-appdata apps must not set nameOverride or fullnameOverride in /repo/apps/selfhosted/demo/values.yaml" in deny with input as {"apps": [app]}
}

test_restic_appdata_rejects_fullname_override if {
  app := object.union(valid_app, {"has_fullname_override": true})
  "restic-appdata apps must not set nameOverride or fullnameOverride in /repo/apps/selfhosted/demo/values.yaml" in deny with input as {"apps": [app]}
}

test_critical_app_cannot_use_no_restore if {
  app := object.union(valid_app, {
    "dr_tier": "critical",
    "dr_restore_mode": "none",
  })
  "critical apps must not use dr.restore.mode none in /repo/apps/selfhosted/demo/app.yaml" in deny with input as {"apps": [app]}
}

test_local_pvc_app_requires_restic_or_disposable_classification if {
  app := object.union(valid_app, {
    "dr_tier": "standard",
    "dr_restore_mode": "gitops",
    "local_persistent_volume_claim_count": 1,
    "has_existing_claim": false,
  })
  "apps with local PVCs must use dr.restore.mode restic-appdata unless dr.tier is disposable in /repo/apps/selfhosted/demo/app.yaml" in deny with input as {"apps": [app]}
}

test_disposable_local_pvc_app_can_skip_restic_restore if {
  app := object.union(valid_app, {
    "dr_tier": "disposable",
    "dr_restore_mode": "none",
    "local_persistent_volume_claim_count": 1,
    "has_existing_claim": false,
  })
  results := deny with input as {"apps": [app]}
  count(results) == 0
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

test_duplicate_generated_name_denied if {
  other_app := object.union(valid_app, {
    "path": "/repo/apps/media/demo",
    "category": "media",
    "generated_name": "selfhosted-demo",
    "app_file": "/repo/apps/media/demo/app.yaml",
    "values_file": "/repo/apps/media/demo/values.yaml",
  })

  "Duplicate generated application name 'selfhosted-demo': /repo/apps/selfhosted/demo and /repo/apps/media/demo" in deny with input as {"apps": [valid_app, other_app]}
}

test_duplicate_app_basename_denied if {
  other_app := object.union(valid_app, {
    "path": "/repo/apps/media/demo",
    "category": "media",
    "generated_name": "media-demo",
    "app_file": "/repo/apps/media/demo/app.yaml",
    "values_file": "/repo/apps/media/demo/values.yaml",
  })

  "Duplicate Argo CD application name 'demo': /repo/apps/selfhosted/demo and /repo/apps/media/demo" in deny with input as {"apps": [valid_app, other_app]}
}
