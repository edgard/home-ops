# Design: n8n Workflow Automation

## Context
n8n is being added to enable workflow automation within the homelab environment. It will run as a self-contained service accessible only via Tailscale VPN, following the existing security and deployment patterns used across all selfhosted apps in the cluster.

**Constraints:**
- Single-node Kind cluster (no high availability)
- VPN-only access (no public exposure)
- Lightweight operation (homelab scale, not production)
- Must follow app-template v4.5.0 house style
- Non-root container preferred
- No resource limits (VPN-protected environment)

**Stakeholders:**
- Homelab operator (primary user)
- Other services that will be automated (home-assistant, media apps, notifications)

## Goals / Non-Goals

**Goals:**
- Provide workflow automation capabilities within the homelab
- Use lightweight SQLite backend (sufficient for homelab scale)
- Maintain security with non-root container and secrets management
- Enable automation of homelab services (home automation, media, notifications)
- Follow existing patterns for consistency and maintainability

**Non-Goals:**
- High availability or multi-replica deployment (single-node cluster)
- PostgreSQL backend (overkill for homelab scale, adds complexity)
- Redis queue (SQLite sufficient for expected workflow volume)
- SMTP configuration (can be added later via n8n UI if needed)
- External OAuth providers (basic auth sufficient for VPN-protected environment)

## Decisions

### Decision 1: SQLite Database Backend
**Choice:** Use SQLite (n8n default) instead of PostgreSQL

**Rationale:**
- Homelab scale: Expected workflow volume is low (<100 workflows, <1000 executions/day)
- Simplicity: No additional database pod/service needed
- Resources: Lower memory footprint, faster startup
- Persistence: SQLite file stored in PVC, survives pod restarts
- Maintenance: No database backups/migrations to manage
- Kopia backup covers the entire data directory including SQLite file

**Alternatives considered:**
- **PostgreSQL**: Rejected due to overhead (additional pod, resources, complexity). PostgreSQL recommended for >100 concurrent executions or high-frequency workflows, which is not the homelab use case.

### Decision 2: Deployment Strategy and Storage
**Choice:** Single replica with `Recreate` strategy, 10Gi PVC on `local-fast` tier

**Rationale:**
- Single-node cluster: Multiple replicas provide no HA benefit
- `Recreate` strategy: Standard homelab pattern, acceptable downtime during updates
- 10Gi storage: Sufficient for workflow data, execution history, and credentials (can be expanded)
- `local-fast` tier: Workflows benefit from fast I/O; data volume is small

**Alternatives considered:**
- **RollingUpdate strategy**: Rejected because SQLite doesn't support concurrent writers
- **5Gi storage**: Too small for execution history retention; 10Gi provides headroom

### Decision 3: Security Context
**Choice:** Non-root container (uid:gid 1000:1000), drop all capabilities

**Rationale:**
- Follows homelab security baseline
- n8n official image supports non-root operation
- No privileged operations required (unlike zigbee2mqtt/qbittorrent)
- VPN-only access provides additional security layer

### Decision 4: Environment Configuration
**Choice:** Minimal environment variables, configure via n8n UI after deployment

**Rationale:**
- Keep deployment lightweight and flexible
- n8n stores configuration in database after first run
- Only set critical variables:
  - `N8N_ENCRYPTION_KEY`: Required, managed via ExternalSecret
  - `N8N_HOST`: Set to `n8n.edgard.org` for webhook URLs
  - `N8N_PORT`: Container port (5678)
  - `GENERIC_TIMEZONE`: Match homelab timezone (Europe/Warsaw)
  - `WEBHOOK_URL`: Set to `https://n8n.edgard.org/` for webhook nodes
- SMTP, OAuth, and other features can be configured later if needed

**Alternatives considered:**
- **Pre-configure SMTP/OAuth via env vars**: Rejected to keep deployment simple; can be added via UI
- **External PostgreSQL**: Already rejected in Decision 1

### Decision 5: Bitwarden Secret Management
**Choice:** Store only `N8N_ENCRYPTION_KEY` in Bitwarden

**Rationale:**
- Encryption key is critical for credential security (encrypts workflow credentials in DB)
- n8n generates random key on first run if not provided; storing in Bitwarden enables disaster recovery
- Key must be stable across pod restarts/redeployments to maintain access to stored credentials
- No other secrets required at deployment time (user creates workflows/credentials in UI)

**Alternatives considered:**
- **Let n8n auto-generate key**: Rejected because key loss means credential data is unrecoverable
- **Store admin credentials in Bitwarden**: Rejected; n8n has no built-in auth at free tier (VPN provides access control)

## Risks / Trade-offs

### Risk 1: SQLite Limitations
- **Risk**: SQLite may struggle with very high workflow execution rates or large webhook volumes
- **Likelihood**: Low (homelab scale, VPN-only access)
- **Impact**: Medium (workflows may queue/delay)
- **Mitigation**: Monitor via Gatus; migrate to PostgreSQL if needed (n8n supports migration)

### Risk 2: Single Replica Downtime
- **Risk**: Pod restarts cause brief workflow execution interruptions
- **Likelihood**: Low (stable deployments, infrequent updates)
- **Impact**: Low (homelab automation is non-critical, can tolerate brief outages)
- **Mitigation**: Use `Recreate` strategy to minimize split-brain scenarios; acceptable trade-off for simplicity

### Risk 3: Encryption Key Loss
- **Risk**: If Bitwarden secret is lost and PVC is deleted, workflow credentials are unrecoverable
- **Likelihood**: Very Low (Bitwarden is backed up; PVC persists across pod restarts)
- **Impact**: High (need to re-enter all credentials in workflows)
- **Mitigation**: Kopia backs up `/mnt/spool/appdata` including PVCs; document key in Bitwarden

### Trade-off: Lightweight vs Full-Featured
- **Trade-off**: Using SQLite instead of PostgreSQL trades potential scale/performance for simplicity
- **Justification**: Homelab workloads are predictable and low-volume; SQLite is sufficient and eliminates operational complexity
- **Escape hatch**: n8n supports database migration if needs change

## Migration Plan

**Initial Deployment:**
1. Add `n8n_encryption_key` to Bitwarden (generate 32-byte random string via `openssl rand -base64 32`)
2. Deploy manifests via Argo CD (auto-sync enabled)
3. Wait for pod to reach Ready state
4. Access `https://n8n.edgard.org` via Tailscale VPN
5. Complete n8n initial setup (create owner account)
6. Verify Gatus monitoring detects the service

**Rollback:**
- Delete Argo CD application: `kubectl delete application -n argocd n8n`
- PVC and data persist (can redeploy without data loss)

**Future Migration to PostgreSQL (if needed):**
1. Deploy PostgreSQL in `selfhosted` namespace
2. Use n8n CLI to export workflows: `n8n export:workflow --all --output=/backup`
3. Update `values.yaml` with PostgreSQL connection string
4. Import workflows to new database: `n8n import:workflow --input=/backup`
5. Validate and delete old PVC

## Open Questions
None. Design is complete and follows established homelab patterns.
