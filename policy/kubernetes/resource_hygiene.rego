package main

import rego.v1

allowed_storage_classes := {"nfs-fast", "nfs-media", "nfs-restic"}

deny contains msg if {
  input.kind == "ExternalSecret"
  object.get(object.get(input.spec, "secretStoreRef", {}), "name", "") != "external-secrets-store"
  msg := sprintf("ExternalSecret/%s must use secretStoreRef.name external-secrets-store", [input.metadata.name])
}

deny contains msg if {
  input.kind == "PersistentVolumeClaim"
  storage_class := object.get(input.spec, "storageClassName", "")
  storage_class != ""
  not allowed_storage_classes[storage_class]
  msg := sprintf("PersistentVolumeClaim/%s must use an approved storageClassName", [input.metadata.name])
}

deny contains msg if {
  some image in pod_images
  lower(image) == sprintf("%s:latest", [trim_suffix(image, ":latest")])
  msg := sprintf("%s/%s must not use latest image tags", [input.kind, input.metadata.name])
}
