# Secrets and credentials

Purpose: distinguish committed secret references from local and encrypted inputs.
Status: current. Reviewed against: `d9a1261970b4d6607056507421a71ad52b5d07ce`.

Bitwarden Secrets Manager owns values. ESO supplies Kubernetes workloads from
the application project; SecretSpec supplies scoped local operator commands.
Separate machine accounts isolate operator access from ESO. Operator-exclusive
zone and OAuth client identifiers belong in the operator project; shared API
tokens remain existing application-project items. One Keychain token
feeds both SecretSpec aliases, and ESO's token is stored in the operator project.
The [maintenance runbook](../operations/secrets-maintenance.md) covers provisioning,
rotation, migration, and the temporary encrypted recovery input. Application
Secret names, keys, refresh behavior, and shared item references remain stable.
The shared store restricts consumer namespaces; it does not isolate allowed
namespaces from each other.

Before changing access, inspect the store, target ExternalSecrets, and the
Ansible or Terraform consumer together. The wiki records wiring and rationale,
never resolved secret values or private runtime logs.

## Sources

- [Operator secret contract](../../../secretspec.toml)
- [Maintenance runbook](../operations/secrets-maintenance.md)

- [ClusterSecretStore](../../../apps/platform-system/external-secrets/manifests/external-secrets-store.clustersecretstore.yaml)
- [External Secrets bootstrap](../../../ansible/roles/platform/tasks/external_secrets.yml)
- [Terraform provider wiring](../../../terraform/main.tf)
- [Role safety policy](../../../policy/ansible/role_safety.rego)

## Related pages

- [Talos bootstrap](talos-bootstrap.md)
- [Terraform](terraform.md)
- [Validation](validation.md)
