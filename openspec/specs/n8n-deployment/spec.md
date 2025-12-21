# n8n-deployment Specification

## Purpose
TBD - created by archiving change add-n8n-selfhosted. Update Purpose after archive.
## Requirements
### Requirement: n8n Workflow Automation Deployment
The homelab SHALL deploy n8n as a self-hosted workflow automation platform in the selfhosted namespace, accessible only via Tailscale VPN.

#### Scenario: n8n deployment with SQLite backend
- **WHEN** the n8n application is deployed via Argo CD
- **THEN** a single-replica pod SHALL be created using the official n8n image
- **AND** the pod SHALL use SQLite as the database backend
- **AND** a 10Gi PersistentVolumeClaim SHALL be mounted for workflow data persistence
- **AND** the pod SHALL run with non-root security context (uid:gid 1000:1000)
- **AND** all Linux capabilities SHALL be dropped except those required for basic operation

#### Scenario: Secure credential storage
- **WHEN** n8n stores workflow credentials
- **THEN** credentials SHALL be encrypted using an encryption key from Bitwarden
- **AND** the encryption key SHALL be fetched via External Secrets Operator
- **AND** the key SHALL be stored in Bitwarden secret `n8n_encryption_key`

#### Scenario: VPN-only access via HTTPRoute
- **WHEN** a user accesses n8n
- **THEN** the service SHALL be exposed at `https://n8n.edgard.org`
- **AND** access SHALL only be possible through the Tailscale VPN
- **AND** the HTTPRoute SHALL route traffic through the Istio gateway
- **AND** TLS SHALL be provided by the wildcard certificate `*.edgard.org`

#### Scenario: Health monitoring
- **WHEN** n8n is running
- **THEN** startup, liveness, and readiness probes SHALL be configured
- **AND** the service SHALL be labeled for Gatus monitoring auto-discovery
- **AND** Gatus SHALL monitor the n8n HTTP endpoint

#### Scenario: Resource allocation
- **WHEN** n8n is deployed
- **THEN** the pod SHALL run with unlimited resources (no limits/requests)
- **AND** the deployment strategy SHALL be `Recreate` (single-node cluster pattern)

### Requirement: n8n Configuration
The n8n deployment SHALL be configured with minimal environment variables following the homelab lightweight principle.

#### Scenario: Essential environment configuration
- **WHEN** n8n starts for the first time
- **THEN** the following environment variables SHALL be set:
  - `N8N_ENCRYPTION_KEY`: Loaded from Bitwarden secret
  - `N8N_HOST`: Set to `n8n.edgard.org`
  - `N8N_PORT`: Set to `5678`
  - `GENERIC_TIMEZONE`: Set to `Europe/Warsaw`
  - `WEBHOOK_URL`: Set to `https://n8n.edgard.org/`
- **AND** additional configuration (SMTP, OAuth, etc.) MAY be configured via the n8n UI after deployment

#### Scenario: Data persistence across restarts
- **WHEN** the n8n pod is restarted or redeployed
- **THEN** all workflow definitions SHALL persist in the SQLite database
- **AND** all execution history SHALL persist in the SQLite database
- **AND** all encrypted credentials SHALL remain accessible using the same encryption key
- **AND** the SQLite database file SHALL be stored in the PersistentVolume

