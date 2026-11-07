# Secrets and credentials

Purpose: explain authoritative Bitwarden values and scoped delivery.
Status: current. Reviewed against: `6aed89365a1ea1eaca88216fdf9bac132a1e18e5`.

Bitwarden Secrets Manager owns all values in one `home-ops` project. ESO supplies
Kubernetes workloads through the existing ClusterSecretStore; SecretSpec supplies
scoped local CLI commands through its single `bitwarden` provider. Both references
must use the same project UUID. They are independent delivery paths to the same
stored items, and the existing application project UUID remains authoritative.

One read-only machine account serves ESO and CLI commands. Its Keychain token
continues to use `home-ops/_provider/access_token`; `eso_bws_access_token` stores the
ESO bootstrap copy in Bitwarden. SecretSpec scopes limit values injected into each
command, while the account can read the whole project. The shared store restricts
consumer namespaces; it does not isolate allowed namespaces from each other.

The [maintenance runbook](../operations/secrets-maintenance.md) covers provisioning,
rotation, and recovery. Preserve item names and IDs during project consolidation.
A credential shared by Terraform and a workload, such as the Tailscale OAuth
secret, stays one item. Independent service credentials retain separate items even
when their present values happen to match; their rotation lifecycles differ.

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
