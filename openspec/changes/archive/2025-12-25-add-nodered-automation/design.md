# Design: Node-RED Integration

## Context

Node-RED is a flow-based programming tool for wiring together hardware devices, APIs, and online services. The user is migrating automation logic from Home Assistant to Node-RED for greater flexibility. This deployment will run Node-RED in the existing Kubernetes homelab cluster, following established patterns for home-automation applications.

**Background:**
- Single-node K3s cluster running on TrueNAS via k3d
- VPN-only access (no public exposure)
- Existing home-automation stack includes: Home Assistant, Mosquitto MQTT, Zigbee2MQTT, Matterbridge, Scrypted
- All apps use bjw-s app-template v4.5.0 for consistency

## Goals / Non-Goals

**Goals:**
- Deploy Node-RED as a reliable, persistent automation engine
- Integrate with existing Mosquitto MQTT broker for device communication
- Follow project conventions for security, persistence, and networking
- Enable web UI access via Istio Gateway with TLS
- Provide health monitoring via Gatus

**Non-Goals:**
- Migrating existing Home Assistant automations (user responsibility)
- Custom Node-RED nodes installation (user can add via UI)
- Setting up credential secrets (Node-RED generates its own on first run)
- High availability (single-node cluster limitation)

## Decisions

### Image Selection
**Decision:** Use official `nodered/node-red:latest` image from Docker Hub

**Rationale:**
- Official image maintained by Node-RED project
- Multi-arch support (amd64, arm64) matches project needs
- Based on Alpine Linux (small footprint)
- Includes Node.js runtime and all dependencies
- Well-documented with strong community support

**Reference:** [Node-RED Docker Documentation](https://nodered.org/docs/getting-started/docker)

### Storage Configuration
**Decision:** Single PVC at `/data` path with 10Gi capacity on `local-fast` storage class

**Rationale:**
- Node-RED stores all user data (flows, settings, credentials, installed nodes) in `/data` directory
- 10Gi matches Home Assistant's allocation (similar data footprint expected)
- `local-fast` storage class appropriate for configuration data
- Default uid/gid 1000 in official image matches our non-root security pattern

**Note:** Per Node-RED docs, the `/data` directory contains:
- `flows.json` - automation workflows
- `flows_cred.json` - encrypted credentials
- `settings.js` - Node-RED configuration
- `node_modules/` - custom installed nodes

### Security Context
**Decision:** Run as non-root user (uid 1000, gid 1000)

**Rationale:**
- Follows project security baseline for all apps
- Official Node-RED image defaults to uid 1000
- No privileged capabilities required (unlike Zigbee2MQTT which needs USB access)
- Aligns with pod security standards

**Security Context:**
```yaml
defaultPodOptions:
  securityContext:
    fsGroup: 1000
    fsGroupChangePolicy: OnRootMismatch
    runAsGroup: 1000
    runAsNonRoot: true
    runAsUser: 1000

containers:
  app:
    securityContext:
      allowPrivilegeEscalation: false
      capabilities:
        drop: ["ALL"]
```

### MQTT Integration
**Decision:** Configure via environment variable pointing to existing Mosquitto service

**Rationale:**
- Mosquitto already deployed at `mqtt://mosquitto.home-automation.svc.cluster.local:1883`
- No authentication currently required (allow_anonymous: true)
- Users configure MQTT nodes in flows via Node-RED UI
- Environment variable provides default broker address as documentation

**Alternative Considered:** No environment variable, let user configure manually
- Rejected: Providing default broker address improves user experience

### Network Exposure
**Decision:** HTTPRoute at `nodered.edgard.org` via Istio Gateway, port 1880

**Rationale:**
- Follows project pattern for all UI-based apps
- Node-RED default port is 1880
- VPN-only access via Tailscale (project security model)
- Istio Gateway provides TLS termination with wildcard cert

### Resource Limits
**Decision:** No resource limits or requests (`resources: {}`)

**Rationale:**
- Project policy: all apps run unlimited in VPN-protected environment
- Eliminates DDoS risk concerns
- Simplifies deployment in single-node cluster

### Timezone Configuration
**Decision:** Set `TZ=America/New_York` environment variable

**Rationale:**
- Node-RED logs use container timezone
- Automation scheduling benefits from correct timezone
- Standard pattern seen in project (k8tz for cluster-wide, TZ for app-specific)

**Note:** User can modify timezone in values.yaml as needed

### Probes Configuration
**Decision:** Enable startup, liveness, and readiness probes on port 1880

**Rationale:**
- Node-RED provides HTTP endpoint at root path
- Startup probe allows time for initial flow loading
- Liveness probe detects hanging processes
- Readiness probe ensures flows are started before routing traffic
- Consistent with Home Assistant and other UI apps

## Risks / Trade-offs

**Risk:** Node-RED credentials generated with system key if not configured
**Mitigation:** Document in comments that users should set `NODE_RED_CREDENTIAL_SECRET` in settings.js after first run for production use. For homelab/VPN-protected use, system-generated key is acceptable.

**Risk:** No backup strategy for Node-RED flows
**Mitigation:** Flows stored in persistent volume, backed up by Kopia server (existing platform service). Users encouraged to export flows periodically or use Node-RED Projects feature (Git integration).

**Trade-off:** Using `:latest` tag instead of pinned version
**Consideration:** Project uses `:latest` for some images, pinned versions for others. For consistency with similar apps, we'll use `:latest` to receive updates automatically. Renovate bot should be configured to detect and propose version pins if needed.

**Risk:** MQTT broker address hardcoded in environment
**Mitigation:** Users can override via settings.js or in flow configuration. Environment variable is purely for convenience.

## Migration Plan

**Deployment Steps:**
1. Create application files in `apps/home-automation/nodered/`
2. ArgoCD ApplicationSet automatically discovers new app
3. ArgoCD syncs and deploys Node-RED
4. Verify deployment health via Gatus
5. Access UI at https://nodered.edgard.org via VPN
6. User manually migrates automations from Home Assistant

**Rollback:**
- Delete `apps/home-automation/nodered/` directory
- ArgoCD will automatically remove deployed resources
- Persistent volume will remain (manual cleanup if needed)

**Dependencies:**
- No changes required to existing apps
- Mosquitto must be running (already deployed)
- Istio Gateway must be healthy (already deployed)

## Open Questions

- **Q:** Should we pin a specific Node-RED version instead of using `:latest`?
  **A:** Using `:latest` for initial deployment, consistent with some other apps. Renovate bot can propose version pins if needed. User can pin manually if desired.

- **Q:** Should we pre-install common Node-RED nodes (e.g., node-red-dashboard)?
  **A:** No. Keep initial deployment minimal. Users can install nodes via UI or by extending the image later.

- **Q:** Should we create a ConfigMap for settings.js?
  **A:** No. Node-RED generates default settings on first run. Users can customize via persistent volume or manual ConfigMap creation later.
