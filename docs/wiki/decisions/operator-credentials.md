# Split operator credentials from Talos secrets

Purpose: record which inputs belong in Git and which belong with the operator.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

[PR #225](https://github.com/edgard/home-ops/pull/225) removed an extra
operator Vault file and restored env-backed inputs for Bitwarden and the
Terraform backend. Talos bootstrap secrets remain in committed Ansible Vault.
The Taskfile and role defaults preserve this split. A page may document the
names and flow of inputs but must not copy their values.

## Sources

- [Credential split, PR #225](https://github.com/edgard/home-ops/pull/225)
- [Taskfile](../../../Taskfile.yaml)
- [Talos Vault file](../../../ansible/roles/talos/files/secrets.vault.yml)
- [Ansible role safety policy](../../../policy/ansible/role_safety.rego)

## Related pages

- [Secrets](../architecture/secrets.md)
- [Talos bootstrap](../architecture/talos-bootstrap.md)
