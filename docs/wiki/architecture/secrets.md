# Secrets and credentials

Purpose: distinguish committed secret references from local and encrypted inputs.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

External Secrets reads Bitwarden Secrets Manager through the shared
`ClusterSecretStore`; applications commit ExternalSecret references rather than
credential values. Bootstrap and Terraform use operator-provided environment
variables. Talos bootstrap material is in an encrypted Ansible Vault file.
Those channels have different scopes and should not be merged into wiki text.

Before changing access, inspect the store, target ExternalSecrets, and the
Ansible or Terraform consumer together. The wiki records wiring and rationale,
never resolved secret values or private runtime logs.

## Sources

- [ClusterSecretStore](../../../apps/platform-system/external-secrets/manifests/external-secrets-store.clustersecretstore.yaml)
- [External Secrets bootstrap](../../../ansible/roles/platform/tasks/external_secrets.yml)
- [Terraform provider wiring](../../../terraform/main.tf)
- [Role safety policy](../../../policy/ansible/role_safety.rego)

## Related pages

- [Talos bootstrap](talos-bootstrap.md)
- [Terraform](terraform.md)
- [Validation](validation.md)
