package main

import rego.v1

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
