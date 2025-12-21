# Change: Add n8n workflow automation to selfhosted apps

## Why
n8n is a workflow automation platform that enables self-hosted integration and automation of various services. Adding n8n to the homelab provides a privacy-focused alternative to cloud-based automation services like Zapier or Make, allowing for automated workflows between homelab services (home automation, media management, notifications) while keeping all data within the VPN-protected environment.

## What Changes
- Add n8n application to `apps/selfhosted/n8n/` following app-template v4.5.0 patterns
- Deploy n8n with SQLite backend (lightweight, sufficient for homelab scale)
- Configure persistent storage for workflow data and credentials
- Expose via Istio gateway with HTTPRoute at `n8n.edgard.org`
- Add Gatus monitoring via service label
- Store encryption key in Bitwarden via ExternalSecret
- Use non-root container security context following house style

## Impact
- **Affected specs**: New capability `n8n-deployment` (project's first OpenSpec specification)
- **Spec deltas**: 
  - **ADDED**: `n8n-deployment` capability with deployment and configuration requirements
- **Affected code**: 
  - New: `apps/selfhosted/n8n/config.yaml`
  - New: `apps/selfhosted/n8n/values.yaml`
  - New: `apps/selfhosted/n8n/manifests/n8n-credentials.externalsecret.yaml`
  - Update: `openspec/project.md` (add n8n to selfhosted apps list and Bitwarden secret keys)
- **Dependencies**: Requires `n8n_encryption_key` secret in Bitwarden (Org `b4b5...`, Proj `1684...`)
- **Deployment**: Single replica, `Recreate` strategy (standard homelab pattern)
- **Resources**: Unlimited (follows VPN-only resource policy)
