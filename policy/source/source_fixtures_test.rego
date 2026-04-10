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
