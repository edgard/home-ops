package main

import rego.v1

protected_backup_namespaces := {"home-automation", "media", "selfhosted"}

deny contains msg if {
  input.apiVersion == "k8up.io/v1"
  input.kind == "Schedule"
  namespace := object.get(input.metadata, "namespace", "")
  not protected_backup_namespaces[namespace]
  msg := sprintf("Schedule/%s must live in a protected backup namespace", [input.metadata.name])
}

deny contains msg if {
  input.apiVersion == "k8up.io/v1"
  input.kind == "Schedule"
  namespace := object.get(input.metadata, "namespace", "")
  rest_url := object.get(object.get(object.get(input.spec, "backend", {}), "rest", {}), "url", "")
  rest_url != sprintf("http://restic.selfhosted.svc.cluster.local:8000/k8up/%s", [namespace])
  msg := sprintf("Schedule/%s rest backend URL must end with /k8up/%s", [input.metadata.name, namespace])
}
