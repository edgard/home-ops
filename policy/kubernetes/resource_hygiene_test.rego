package main

import rego.v1

test_nfs_controller_must_not_run_snapshotter_without_snapshot_crds if {
  deployment := {
    "apiVersion": "apps/v1",
    "kind": "Deployment",
    "metadata": {"name": "csi-nfs-controller"},
    "spec": {"template": {"spec": {"containers": [{"name": "nfs"}, {"name": "csi-snapshotter"}]}}},
  }
  "Deployment/csi-nfs-controller must not run csi-snapshotter without snapshot CRDs" in deny with input as deployment
}

test_externalsecret_requires_canonical_secret_store if {
  secret := {
    "apiVersion": "external-secrets.io/v1",
    "kind": "ExternalSecret",
    "metadata": {"name": "demo"},
    "spec": {"secretStoreRef": {"name": "other-store"}},
  }
  "ExternalSecret/demo must use secretStoreRef.name external-secrets-store" in deny with input as secret
}

test_pvc_storage_class_must_be_approved if {
  pvc := {
    "apiVersion": "v1",
    "kind": "PersistentVolumeClaim",
    "metadata": {"name": "data"},
    "spec": {"storageClassName": "fast-ssd"},
  }
  "PersistentVolumeClaim/data must use an approved storageClassName" in deny with input as pvc
}

test_latest_image_tags_are_rejected if {
  pod := {
    "apiVersion": "apps/v1",
    "kind": "Deployment",
    "metadata": {"name": "demo"},
    "spec": {
      "template": {
        "spec": {
          "containers": [{"name": "app", "image": "ghcr.io/example/app:latest"}],
        },
      },
    },
  }
  "Deployment/demo must not use latest image tags" in deny with input as pod
}
