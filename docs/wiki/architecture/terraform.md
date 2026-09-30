# Terraform and external infrastructure

Purpose: locate Cloudflare, Tailscale, provider secrets, and state boundaries.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

OpenTofu manages Cloudflare DNS and Tailscale resources from this repo. Its
remote S3-compatible backend and Bitwarden data sources are configured in
Terraform; operator credentials are supplied outside Git. Planning and applying
are Taskfile and Ansible operations, distinct from Argo CD application sync.

The offline Terraform lint target validates configuration without connecting
to the real backend. A successful lint does not constitute an applied plan.

## Sources

- [Terraform root module](../../../terraform/main.tf)
- [Cloudflare module](../../../terraform/cloudflare/dns.tf)
- [Tailscale resources](../../../terraform/tailscale.tf)
- [Tofu role](../../../ansible/roles/tofu/tasks)
- [Operator tasks](../../../Taskfile.yaml)

## Related pages

- [Networking](networking.md)
- [Secrets](secrets.md)
- [Validation](validation.md)
