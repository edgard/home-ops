# Terraform and external infrastructure

Purpose: locate Cloudflare, Tailscale, provider secrets, and state boundaries.
Status: current. Reviewed against: `d9a1261970b4d6607056507421a71ad52b5d07ce`.

OpenTofu manages Cloudflare DNS and Tailscale resources from this repo. Its
remote S3-compatible backend remains configured in Terraform. SecretSpec supplies
backend credentials and native provider variables; credential variables are
sensitive, while the zone ID is nonsensitive. Sensitivity masks display and does
not encrypt state. The [migration runbook](../operations/secrets-maintenance.md)
requires a protected state backup and removal of only retired data-source entries
before a zero-change infrastructure plan. Planning and applying
are Taskfile and Ansible operations, distinct from Argo CD application sync.

The offline Terraform lint target validates configuration without connecting
to the real backend. A successful lint does not constitute an applied plan.

## Sources

- [Operator secret contract](../../../secretspec.toml)
- [Maintenance runbook](../operations/secrets-maintenance.md)

- [Terraform root module](../../../terraform/main.tf)
- [Cloudflare module](../../../terraform/cloudflare/dns.tf)
- [Tailscale resources](../../../terraform/tailscale.tf)
- [Tofu role](../../../ansible/roles/tofu/tasks)
- [Operator tasks](../../../Taskfile.yaml)

## Related pages

- [Networking](networking.md)
- [Secrets](secrets.md)
- [Validation](validation.md)
