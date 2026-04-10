package main

import rego.v1

valid_app_template := {
  "app_file": "/repo/apps/selfhosted/demo/app.yaml",
  "values_file": "/repo/apps/selfhosted/demo/values.yaml",
  "chart_repo": "oci://ghcr.io/bjw-s-labs/helm/app-template",
  "chart_version": "4.6.2",
  "values_top_level_keys": ["defaultPodOptions", "controllers", "service", "route", "persistence"],
  "controller_keys": ["main"],
  "service_keys": ["main"],
  "route_keys": ["main"],
  "default_pod_security_context": {
    "fsGroup": "1000",
    "fsGroupChangePolicy": "OnRootMismatch",
    "runAsGroup": "1000",
    "runAsNonRoot": "true",
    "runAsUser": "1000",
  },
  "service_main_controller": "main",
  "service_main_ports": ["http"],
  "service_main_annotations": {
    "gatus.edgard.org/enabled": "true",
  },
  "route_main_hostnames": ["demo.edgard.org"],
  "route_main_backend_identifiers": ["main"],
  "route_main_annotations": {
    "gethomepage.dev/enabled": "true",
    "gethomepage.dev/name": "Demo",
    "gethomepage.dev/group": "Selfhosted",
    "gethomepage.dev/icon": "demo.svg",
    "gethomepage.dev/app": "demo",
  },
  "raw_httproute_manifest_paths": [],
}

valid_manifest := {
  "path": "/repo/apps/selfhosted/demo/manifests/demo-config.configmap.yaml",
  "relative_path": "apps/selfhosted/demo/manifests/demo-config.configmap.yaml",
  "basename": "demo-config.configmap.yaml",
  "top_level_keys": ["apiVersion", "kind", "metadata", "spec"],
  "metadata_keys": ["name", "namespace"],
}

valid_root_manifest := {
  "path": "/repo/argocd/projects/platform-system.appproject.yaml",
  "relative_path": "argocd/projects/platform-system.appproject.yaml",
  "basename": "platform-system.appproject.yaml",
  "top_level_keys": ["apiVersion", "kind", "metadata", "spec"],
  "metadata_keys": ["name", "namespace"],
}

test_valid_source_conventions_pass if {
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

test_rejects_argocd_raw_httproute_manifests if {
  app := {
    "app_file": "/repo/apps/argocd/argocd/app.yaml",
    "values_file": "/repo/apps/argocd/argocd/values.yaml",
    "chart_repo": "oci://ghcr.io/argoproj/argo-helm/argo-cd",
    "chart_version": "9.4.17",
    "raw_httproute_manifest_paths": ["/repo/apps/argocd/argocd/manifests/argocd.httproute.yaml"],
  }

  "argo-cd chart apps must declare HTTPRoute via values.yaml server.httproute instead of a raw manifest in /repo/apps/argocd/argocd/values.yaml" in deny with input as {"apps": [app], "manifests": [valid_manifest]}
}

test_rejects_non_prefixed_manifest_filename if {
  manifest := object.union(valid_manifest, {
    "path": "/repo/apps/selfhosted/demo/manifests/config.configmap.yaml",
    "relative_path": "apps/selfhosted/demo/manifests/config.configmap.yaml",
    "basename": "config.configmap.yaml",
  })
  "owned manifest filename must start with the owning app or resource name in /repo/apps/selfhosted/demo/manifests/config.configmap.yaml" in deny with input as {"apps": [valid_app_template], "manifests": [manifest]}
}

test_rejects_non_canonical_manifest_field_order if {
  manifest := object.union(valid_manifest, {"top_level_keys": ["kind", "apiVersion", "metadata", "spec"]})
  "owned manifest must order fields as apiVersion, kind, metadata, spec in /repo/apps/selfhosted/demo/manifests/demo-config.configmap.yaml" in deny with input as {"apps": [valid_app_template], "manifests": [manifest]}
}

test_rejects_spec_after_other_top_level_fields if {
  manifest := object.union(valid_manifest, {"top_level_keys": ["apiVersion", "kind", "metadata", "data", "spec"]})
  "owned manifest must order fields as apiVersion, kind, metadata, spec in /repo/apps/selfhosted/demo/manifests/demo-config.configmap.yaml" in deny with input as {"apps": [valid_app_template], "manifests": [manifest]}
}

test_allows_manifest_without_spec if {
  manifest := object.union(valid_manifest, {"top_level_keys": ["apiVersion", "kind", "metadata", "data"]})
  results := deny with input as {"apps": [valid_app_template], "manifests": [manifest]}
  count(results) == 0
}

test_rejects_non_canonical_metadata_field_order if {
  manifest := object.union(valid_manifest, {"metadata_keys": ["annotations", "name", "namespace"]})
  "metadata keys must order fields as name, namespace, labels, annotations in /repo/apps/selfhosted/demo/manifests/demo-config.configmap.yaml" in deny with input as {"apps": [valid_app_template], "manifests": [manifest]}
}
