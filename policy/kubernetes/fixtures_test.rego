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
