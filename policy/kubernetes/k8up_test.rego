package main

import rego.v1

valid_k8up_schedule := {
  "apiVersion": "k8up.io/v1",
  "kind": "Schedule",
  "metadata": {
    "name": "appdata",
    "namespace": "selfhosted",
  },
  "spec": {
    "backend": {
      "rest": {
        "url": "http://restic.selfhosted.svc.cluster.local:8000/k8up/selfhosted",
      },
    },
  },
}

test_valid_k8up_schedule_passes if {
  results := deny with input as valid_k8up_schedule
  count(results) == 0
}

test_k8up_schedule_requires_protected_namespace if {
  doc := object.union(valid_k8up_schedule, {"metadata": {"name": "appdata", "namespace": "default"}})
  "Schedule/appdata must live in a protected backup namespace" in deny with input as doc
}

test_k8up_schedule_url_must_match_namespace if {
  doc := object.union(valid_k8up_schedule, {"spec": {"backend": {"rest": {"url": "http://restic.selfhosted.svc.cluster.local:8000/k8up/media"}}}})
  "Schedule/appdata rest backend URL must end with /k8up/selfhosted" in deny with input as doc
}
