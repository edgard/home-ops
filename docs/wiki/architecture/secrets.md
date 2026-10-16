# Secrets and credentials

Purpose: explain authoritative Bitwarden values and scoped delivery.
Status: current. Reviewed against: `ae198e1dcee21682caa39016c64839a7e52a416c`.

Bitwarden Secrets Manager owns values. ESO supplies Kubernetes workloads from
the application project; SecretSpec supplies scoped local CLI commands.
This homelab uses one shared read-only machine account for both projects.
SecretSpec scopes limit values injected into each command; they do not isolate
the account's access. ESO's token can also read CLI-project secrets.
CLI-exclusive
zone and OAuth client identifiers belong in the CLI project; shared API
tokens remain existing application-project items. One Keychain token
feeds both SecretSpec aliases, and the same token is stored in the CLI project
for ESO bootstrap.
The [maintenance runbook](../operations/secrets-maintenance.md) covers provisioning,
rotation and recovery. Application
Secret names, keys, refresh behavior, and shared item references remain stable.
The shared store restricts consumer namespaces; it does not isolate allowed
namespaces from each other.

Before changing access, inspect the store, target ExternalSecrets, and the
Ansible or Terraform consumer together. The wiki records wiring and rationale,
never resolved secret values or private runtime logs.

The active Vault maintenance path and global CLI secret exports are
retired. Historical source snapshots preserve the earlier workflow; current
recovery requires Bitwarden and the CLI credential. Ignored credential,
state, plan, crash, and backup paths remain protected from accidental commits.

## Sources

- [CLI secret contract](../../../secretspec.toml)
- [Maintenance runbook](../operations/secrets-maintenance.md)

- [ClusterSecretStore](../../../apps/platform-system/external-secrets/manifests/external-secrets-store.clustersecretstore.yaml)
- [External Secrets bootstrap](../../../ansible/roles/platform/tasks/external_secrets.yml)
- [Terraform provider wiring](../../../terraform/main.tf)
- [Role behavior scenarios](../../../tests/integration)

## Related pages

- [Talos bootstrap](talos-bootstrap.md)
- [Terraform](terraform.md)
- [Validation](validation.md)
