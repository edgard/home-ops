package main

import rego.v1

vendored_manifest_exemptions := {
  "apps/platform-system/gateway-api/manifests/gateway-api-crds.yaml",
}

deny contains msg if {
  some manifest in input.manifests
  not is_vendored_manifest(manifest)
  not has_expected_manifest_filename(manifest)
  msg := sprintf("owned manifest filename must start with the owning app or resource name in %s", [manifest.path])
}

deny contains msg if {
  some manifest in input.manifests
  not is_vendored_manifest(manifest)
  not has_expected_manifest_top_level_order(manifest)
  msg := sprintf("owned manifest must order fields as apiVersion, kind, metadata, spec in %s", [manifest.path])
}

deny contains msg if {
  some manifest in input.manifests
  not is_vendored_manifest(manifest)
  not has_expected_metadata_order(manifest)
  msg := sprintf("metadata keys must order fields as name, namespace, labels, annotations in %s", [manifest.path])
}

is_vendored_manifest(manifest) if {
  vendored_manifest_exemptions[manifest.relative_path]
}

has_expected_manifest_filename(manifest) if {
  startswith(manifest.relative_path, "apps/")
  startswith(manifest.basename, sprintf("%s-", [manifest_owner_name(manifest)]))
}

has_expected_manifest_filename(manifest) if {
  not startswith(manifest.relative_path, "apps/")
  startswith(manifest.basename, sprintf("%s.", [manifest_owner_name(manifest)]))
}

manifest_owner_name(manifest) := app_name if {
  startswith(manifest.relative_path, "apps/")
  parts := split(manifest.relative_path, "/")
  count(parts) >= 5
  app_name := parts[2]
}

manifest_owner_name(manifest) := basename_prefix if {
  not startswith(manifest.relative_path, "apps/")
  basename_parts := split(manifest.basename, ".")
  basename_prefix := basename_parts[0]
}

has_expected_manifest_top_level_order(manifest) if {
  keys := object.get(manifest, "top_level_keys", [])
  count(keys) >= 3
  keys[0] == "apiVersion"
  keys[1] == "kind"
  keys[2] == "metadata"
  spec_order_is_valid(keys)
}

spec_order_is_valid(keys) if {
  not list_contains(keys, "spec")
}

spec_order_is_valid(keys) if {
  list_contains(keys, "spec")
  count(keys) >= 4
  keys[3] == "spec"
}

has_expected_metadata_order(manifest) if {
  keys := object.get(manifest, "metadata_keys", [])
  ordered_if_present(keys, "name", "namespace")
  ordered_if_present(keys, "name", "labels")
  ordered_if_present(keys, "name", "annotations")
  ordered_if_present(keys, "namespace", "labels")
  ordered_if_present(keys, "namespace", "annotations")
  ordered_if_present(keys, "labels", "annotations")
}
