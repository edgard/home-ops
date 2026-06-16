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

test_requires_gatus_sidecar_template_for_routed_apps if {
  app := object.union(valid_app_template, {
    "route_main_annotations": {
      "gethomepage.dev/enabled": "true",
      "gethomepage.dev/name": "Demo",
      "gethomepage.dev/group": "Selfhosted",
      "gethomepage.dev/icon": "demo.svg",
      "gethomepage.dev/app": "demo",
      "gatus.home-operations.com/endpoint": "",
    },
  })
  "route.main must define gatus.home-operations.com/endpoint for routed apps in /repo/apps/selfhosted/demo/values.yaml" in deny with input as {"apps": [app], "manifests": [valid_manifest]}
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

test_requires_k8up_backup_annotation_on_local_pvcs if {
  app := object.union(valid_app_template, {
    "local_persistent_volume_claims": [{
      "name": "data",
      "backup_annotation": "",
    }],
  })
  "local persistentVolumeClaim data must set k8up.io/backup: \"true\" in /repo/apps/selfhosted/demo/values.yaml" in deny with input as {"apps": [app], "manifests": [valid_manifest]}
}

test_rejects_k8up_backup_annotation_on_existing_claims if {
  app := object.union(valid_app_template, {
    "existing_claim_persistence": [{
      "name": "media",
      "backup_annotation": "true",
    }],
  })
  "existingClaim persistence media must not set k8up.io/backup in /repo/apps/selfhosted/demo/values.yaml" in deny with input as {"apps": [app], "manifests": [valid_manifest]}
}

test_rejects_name_override_on_k8up_backed_apps if {
  app := object.union(valid_app_template, {
    "has_name_override": true,
  })
  "K8up-backed app-template values must not set nameOverride in /repo/apps/selfhosted/demo/values.yaml" in deny with input as {"apps": [app], "manifests": [valid_manifest]}
}

test_rejects_fullname_override_on_k8up_backed_apps if {
  app := object.union(valid_app_template, {
    "has_fullname_override": true,
  })
  "K8up-backed app-template values must not set fullnameOverride in /repo/apps/selfhosted/demo/values.yaml" in deny with input as {"apps": [app], "manifests": [valid_manifest]}
}
