# Terraform and external infrastructure

Purpose: locate Cloudflare, Tailscale, provider secrets, and state boundaries.
Status: current. Reviewed against: `9f966763020631cd9bab2de5ddd8471434b71876`.

OpenTofu manages Cloudflare DNS and Tailscale resources from this repo. Its
remote S3-compatible backend remains configured in Terraform. SecretSpec supplies
backend credentials and native provider variables from the shared Bitwarden project; credential variables are
sensitive, while the zone ID is nonsensitive. Sensitivity masks display and does
not encrypt state. The root module preserves the legacy sensitivity flag on
managed zone-ID attributes, so changing secret delivery does not plan writes
solely to remove state sensitivity. The input variable remains nonsensitive.
The [migration runbook](../operations/secrets-maintenance.md)
requires a protected state backup and removal of only retired data-source entries
before a zero-change infrastructure plan. Planning and applying
are Taskfile and Ansible operations, distinct from Argo CD application sync.

The offline Terraform lint target initializes without a backend in temporary
provider data and validates with the committed root provider lock read-only.
Provider checksums cover macOS ARM64 and Linux AMD64; `tf:clean` preserves the
lock. Provider changes update their declarations and lock together, using the
OpenTofu registry. State, plans, and credentials remain ignored. A successful
lint does not constitute an applied plan.

The Cloudflare provider pin and Renovate compatibility limit avoid the
[query-parameter regression](https://github.com/cloudflare/terraform-provider-cloudflare/issues/7396)
that forces updates to unchanged DNS records. Lift the limit only after a real
zero-change plan verifies a fixed provider. DNS attributes and resource addresses
remain unchanged; no lifecycle rule suppresses DNS changes.

## Sources

- [CLI secret contract](../../../secretspec.toml)
- [Maintenance runbook](../operations/secrets-maintenance.md)

- [Terraform root module](../../../terraform/main.tf)
- [Provider lock](../../../terraform/.terraform.lock.hcl)
- [Dependency compatibility limits](../../../.renovaterc.json5)
- [Cloudflare module](../../../terraform/cloudflare/dns.tf)
- [Tailscale resources](../../../terraform/tailscale.tf)
- [Tofu role](../../../ansible/roles/tofu/tasks)
- [CLI tasks](../../../Taskfile.yaml)

## Related pages

- [Networking](networking.md)
- [Secrets](secrets.md)
- [Validation](validation.md)
