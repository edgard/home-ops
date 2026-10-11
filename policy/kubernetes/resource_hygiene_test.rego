package main

import rego.v1

test_istio_validation_webhooks_must_fail_closed if {
  some name in {"istiod-default-validator", "istio-validator-platform-system"}
  webhook := {
    "apiVersion": "admissionregistration.k8s.io/v1",
    "kind": "ValidatingWebhookConfiguration",
    "metadata": {"name": name},
    "webhooks": [{"name": "validation.istio.io", "failurePolicy": "Ignore"}],
  }
  sprintf("ValidatingWebhookConfiguration/%s must fail closed for validation.istio.io", [name]) in deny with input as webhook
}

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

test_external_secret_requires_store_kind if {
  secret := {"kind": "ExternalSecret", "metadata": {"name": "demo"}, "spec": {"secretStoreRef": {"name": "external-secrets-store", "kind": "SecretStore"}}}
  "ExternalSecret/demo must use ClusterSecretStore" in deny with input as secret
}

test_populated_secret_denied if {
  secret := {"kind": "Secret", "metadata": {"name": "demo"}, "stringData": {"password": "synthetic"}}
  "Secret/demo must obtain values from a controller or operator bootstrap" in deny with input as secret
}

test_empty_controller_secret_allowed if {
  secret := {"kind": "Secret", "metadata": {"name": "demo"}, "data": {"password": ""}}
  result := deny with input as secret
  count(result) == 0
}

test_store_namespace_restrictions_required if {
  store := {"kind": "ClusterSecretStore", "metadata": {"name": "external-secrets-store"}, "spec": {}}
  "ClusterSecretStore/external-secrets-store must restrict consumer namespaces" in deny with input as store
}

test_namespace_order_is_not_a_security_difference if {
  store := {"kind": "ClusterSecretStore", "metadata": {"name": "external-secrets-store"}, "spec": {"conditions": [{"namespaces": ["selfhosted", "media", "platform-system", "argocd"]}]}}
  result := deny with input as store
  count(result) == 0
}
