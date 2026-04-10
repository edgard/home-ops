package main

import rego.v1

test_valid_manifest_conventions_pass if {
  results := deny with input as {"apps": [valid_app_template], "manifests": [valid_manifest, valid_root_manifest]}
  count(results) == 0
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
