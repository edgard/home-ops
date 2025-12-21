# Implementation Tasks

## 1. Setup Bitwarden Secret
- [x] 1.1 Generate encryption key and add `n8n_encryption_key` to Bitwarden (Org `b4b5...`, Proj `1684...`)

## 2. Create n8n Application Structure
- [x] 2.1 Create `apps/selfhosted/n8n/config.yaml` with app-template v4.5.0 chart reference
- [x] 2.2 Create `apps/selfhosted/n8n/manifests/n8n-credentials.externalsecret.yaml` for encryption key
- [x] 2.3 Create `apps/selfhosted/n8n/values.yaml` with n8n deployment configuration

## 3. Configure n8n Deployment
- [x] 3.1 Set n8n container image (docker.io/n8nio/n8n, use stable tag)
- [x] 3.2 Configure SQLite database (lightweight, no PostgreSQL needed for homelab)
- [x] 3.3 Configure persistent storage (10Gi PVC on local-fast tier)
- [x] 3.4 Set environment variables (timezone, webhook URL, encryption key from secret)
- [x] 3.5 Configure non-root security context (uid:gid 1000:1000, drop all capabilities)
- [x] 3.6 Add health probes (startup, liveness, readiness)
- [x] 3.7 Set resources to unlimited (follows house policy)

## 4. Configure Networking
- [x] 4.1 Create service with Gatus monitoring label
- [x] 4.2 Create HTTPRoute pointing to Istio gateway at `n8n.edgard.org`

## 5. Update Documentation
- [x] 5.1 Add `n8n_encryption_key` to Bitwarden secret keys list in `openspec/project.md`
- [x] 5.2 Add n8n to selfhosted apps list in `openspec/project.md`

## 6. Validation
- [x] 6.1 Run `task lint` to validate YAML formatting
- [x] 6.2 Verify Argo CD can sync the application
- [x] 6.3 Access n8n at `https://n8n.edgard.org` via Tailscale VPN
- [x] 6.4 Confirm Gatus monitoring is active
- [x] 6.5 Test workflow creation and execution
