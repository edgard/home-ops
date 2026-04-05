package main

import rego.v1

base_deployment := {
  "apiVersion": "apps/v1",
  "kind": "Deployment",
  "metadata": {
    "name": "demo",
    "labels": {
      "helm.sh/chart": "app-template-4.6.2",
    },
  },
  "spec": {
    "replicas": 1,
    "strategy": {"type": "Recreate"},
    "template": {
      "spec": {
        "securityContext": {"runAsNonRoot": true},
        "containers": [{
          "name": "app",
          "image": "ghcr.io/example/app:v1.2.3",
          "securityContext": {
            "allowPrivilegeEscalation": false,
            "capabilities": {"drop": ["ALL"]},
          },
        }],
      },
    },
  },
}

test_valid_app_template_workload_passes if {
  results := deny with input as base_deployment
  count(results) == 0
}

test_app_template_requires_single_replica if {
  doc := object.union(base_deployment, {"spec": object.union(base_deployment.spec, {"replicas": 2})})
  "Deployment/demo must set replicas to 1" in deny with input as doc
}

test_app_template_requires_recreate_strategy if {
  doc := object.union(base_deployment, {"spec": object.union(base_deployment.spec, {"strategy": {"type": "RollingUpdate"}})})
  "Deployment/demo must use Recreate strategy" in deny with input as doc
}

test_app_template_requires_allow_privilege_escalation_false if {
  bad_container := object.union(base_deployment.spec.template.spec.containers[0], {"securityContext": {"allowPrivilegeEscalation": true, "capabilities": {"drop": ["ALL"]}}})
  doc := object.union(base_deployment, {"spec": object.union(base_deployment.spec, {"template": {"spec": object.union(base_deployment.spec.template.spec, {"containers": [bad_container]})}})})
  "Deployment/demo container app must set allowPrivilegeEscalation to false" in deny with input as doc
}

test_app_template_requires_drop_all_capabilities if {
  bad_container := object.union(base_deployment.spec.template.spec.containers[0], {"securityContext": {"allowPrivilegeEscalation": false, "capabilities": {"drop": ["NET_BIND_SERVICE"]}}})
  doc := object.union(base_deployment, {"spec": object.union(base_deployment.spec, {"template": {"spec": object.union(base_deployment.spec.template.spec, {"containers": [bad_container]})}})})
  "Deployment/demo container app must drop ALL capabilities" in deny with input as doc
}

test_app_template_requires_run_as_non_root_by_default if {
  doc := object.union(base_deployment, {"spec": object.union(base_deployment.spec, {"template": {"spec": {"securityContext": {"runAsNonRoot": false}, "containers": base_deployment.spec.template.spec.containers}}})})
  "Deployment/demo container app must run as non-root" in deny with input as doc
}

test_linuxserver_images_are_exempt_from_run_as_non_root if {
  exempt_container := object.union(base_deployment.spec.template.spec.containers[0], {"image": "lscr.io/linuxserver/sonarr:4.0.17"})
  doc := object.union(base_deployment, {"spec": object.union(base_deployment.spec, {"template": {"spec": {"securityContext": {"runAsNonRoot": false}, "containers": [exempt_container]}}})})
  results := deny with input as doc
  count(results) == 0
}

test_tailscale_is_exempt_from_container_security_rules if {
  doc := object.union(base_deployment, {"spec": object.union(base_deployment.spec, {"template": {"spec": {"securityContext": {"runAsNonRoot": false}, "containers": [{
    "name": "tailscale",
    "image": "ghcr.io/tailscale/tailscale:v1.94.2",
    "securityContext": {"capabilities": {"add": ["NET_ADMIN"]}},
  }]}}})})
  results := deny with input as doc
  count(results) == 0
}

test_httproute_requires_expected_hostname_and_parent_ref if {
  route := {
    "apiVersion": "gateway.networking.k8s.io/v1",
    "kind": "HTTPRoute",
    "metadata": {"name": "demo"},
    "spec": {
      "parentRefs": [{"name": "other", "namespace": "platform-system", "sectionName": "https"}],
      "hostnames": ["demo.example.com"],
    },
  }
  "HTTPRoute/demo hostname demo.example.com must end with .edgard.org" in deny with input as route
  "HTTPRoute/demo must target gateway/platform-system section https" in deny with input as route
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
