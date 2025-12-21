# Project Context

## Purpose
Home Operations (home-ops) is a GitOps-managed Kubernetes homelab infrastructure running on Kind (Kubernetes in Docker). The project automates deployment of home automation, media management, and self-hosted services with a focus on security, reproducibility, and VPN-only access.

## Tech Stack
- **Container Orchestration**: Kubernetes (Kind cluster)
- **GitOps**: Argo CD with ApplicationSets
- **Infrastructure as Code**: Terraform (Cloudflare, Tailscale)
- **Package Management**: Helm, Helmfile
- **Custom Controllers**: Python 3.14 + Kopf framework
- **Service Mesh**: Istio (Gateway API)
- **Secrets Management**: External Secrets Operator + Bitwarden
- **Storage**: local-path-provisioner (fast/bulk tiers)
- **Backup**: Kopia server
- **Monitoring**: Gatus, Falco
- **VPN**: Tailscale subnet router

## Project Conventions

### Code Style
- **YAML Formatting**: Use `.yamlfmt` and `.yamllint` configs. Run `task lint` before commits.
- **File Naming**: Kebab-case. Manifests follow `{app}-{descriptor}.{kind}.yaml` pattern.
- **Indentation**: 2 spaces. No tabs. Keep files ASCII-compatible.
- **Documentation**: Update `AGENTS.md` in same PR when changing automation/commands.

### Architecture Patterns
- **GitOps Model**: All cluster state declared in Git. Argo CD syncs from main branch.
- **App Structure**: `apps/<group>/<app>/` contains `config.yaml`, `values.yaml`, and `manifests/` directory.
- **Sync Waves**: Ordered deployment via Argo CD sync-wave annotations (-4 to 0).
- **Security**: VPN-only access (no public exposure). Non-root containers by default. Secrets from Bitwarden only.
- **Helm Pattern**: Prefer `ghcr.io/bjw-s-labs/helm/app-template` v4.5.0 for consistent app structure.
- **Resource Limits**: All apps run unlimited (`resources: {}`). VPN-only eliminates DDoS risk.

### Testing Strategy
- **Validation**: Pre-commit linting via `task lint` (yamlfmt, yamllint, prettier).
- **Bootstrap Testing**: `task bootstrap:create` spins up full cluster for integration testing.
- **Manual Verification**: Test service access via Tailscale VPN after deployment.

### Git Workflow
- **Branching**: Work on feature branches, merge to main via PR.
- **Commits**: Meaningful messages focusing on "why" over "what". Follow existing style (see `git log`).
- **Safety**: No destructive git ops. No decrypted secrets in commits.
- **Pre-commit Hooks**: Auto-format YAML on commit. Amend if hooks modify files.

## Domain Context

### Kubernetes Homelab
- **Cluster Type**: Kind (single-node, Docker-based)
- **Bootstrap**: `bootstrap_kind.py` handles Docker context/network setup, then `helmfile.yaml.gotmpl` installs core platform
- **Namespaces**: Grouped by function (argocd, platform-system, home-automation, media, selfhosted, etc.)
- **Storage Tiers**: `local-fast` (default, `/mnt/spool/appdata`) and `local-bulk` (`/mnt/dpool`)

### Networking & DNS
- **Access Model**: VPN-only via Tailscale. Zero external exposure.
- **Ingress**: Istio Gateway API (`gateway`) with wildcard TLS cert (*.edgard.org).
- **Public DNS**: Managed via Terraform (`terraform/cloudflare/dns.tf`).
- **Internal DNS**: `external-dns` syncs HTTPRoutes to Unifi DNS (192.168.1.1). `coredns` forwards `edgard.org` queries to Unifi.
- **Split-DNS**: DNSEndpoints in `terraform/cloudflare/dnsendpoints.tf` ensure Terraform and external-dns stay in sync.

### Security Model
- **Secrets**: All secrets stored in Bitwarden (Org `b4b5...`, Proj `1684...`). ESO fetches via `external-secrets-sdk-server`.
- **TLS**: cert-manager issues certs via Cloudflare ACME DNS-01 challenge.
- **Runtime Security**: Falco monitors syscalls, sends alerts to homelab-controller for Telegram digest.
- **Container Security**: Non-root by default, drop all capabilities, read-only root filesystem where possible.

### App Categories
- **Home Automation**: home-assistant, mosquitto, zigbee2mqtt
- **Media**: Jellyfin, Radarr, Sonarr, Bazarr, Prowlarr, qBittorrent (via Gluetun VPN), Recyclarr, Unpackerr
- **Self-hosted**: Atuin, Changedetection, Gatus, Homepage, Karakeep, Paperless-ngx
- **Platform**: cert-manager, external-dns, external-secrets, Falco, Gateway API, homelab-controller, Istio, Kopia, Multus, Reloader, Tailscale

## Important Constraints
- **VPN-Only Access**: All services require Tailscale connection. No public internet exposure.
- **Single-Node Cluster**: Kind-based. Limited HA options. Use `Recreate` deployment strategy.
- **Host Dependencies**: Requires `/mnt/spool/appdata` and `/mnt/dpool` on Docker host.
- **Docker Context**: Must use Kind's Docker context (handled by `bootstrap_kind.py`).
- **Secret Keys**: Bitwarden secrets must match exact keys listed in AGENTS.md.
- **Resource Philosophy**: No limits/requests set. Trust VPN-protected environment.

## External Dependencies
- **Bitwarden Secrets Manager**: Secret storage (Org `b4b5...`, Proj `1684...`). Requires `BWS_ACCESS_TOKEN` env var.
- **Cloudflare**: DNS and ACME TLS challenge. Terraform-managed.
- **Tailscale**: VPN access layer. OAuth credentials for Terraform, auth key in Bitwarden for subnet router.
- **Unifi Network**: Internal DNS server (192.168.1.1). Receives DNSEndpoint updates from external-dns.
- **Docker**: Cluster runtime. Requires Docker daemon with overlay2 storage driver.
- **Telegram**: Alert delivery for Gatus and Falco (via homelab-controller).

---

# Operational Reference

This section contains runtime operational details for day-to-day maintenance.

## Repo Layout & Bootstrap

- **`bootstrap/`**: Kind config, `bootstrap_kind.py` (docker context/network plumbing), and `helmfile.yaml.gotmpl`.
  - **Process**: `task bootstrap:create` brings up Kind, patches kubeconfig, creates `bitwarden-credentials` (from `BWS_ACCESS_TOKEN`), and runs helmfile.
  - **Helmfile**: Installs local-path-provisioner (demotes standard SC), Multus, cert-manager, ESO (wait for CM), Argo CD.
  - **Secrets**: Stored in Bitwarden (Org `b4b5...`, Proj `1684...`). ESO fetches via `external-secrets-sdk-server` (TLS via cert-manager).
- **`argocd/`**: `root.app.yaml` and `appsets/apps.appset.yaml` (ordered by sync-wave).
- **`apps/<group>/<app>/`**: `config.yaml` (chart source), `values.yaml`, `manifests/` (synced).
- **`terraform/`**: Cloudflare + Tailscale config (B2 backend).

## Argo CD Mechanics

- **Sync Waves**: `-4` System/CRDs, `-3` Controllers/DNS/VPN, `-2` Mesh, `-1` k8tz, `0` Apps.
- **ServerSideApply**: Enabled globally. Progressive syncs/rollouts disabled.
- **Gateway API**: Istio gateway (`gateway`) for all ingress. VPN-only access.
- **DNS Split-Horizon**: 
  - Public (Cloudflare): `terraform/cloudflare/dns.tf`
  - Internal (Unifi): `external-dns` syncs HTTPRoutes → 192.168.1.241, DNSEndpoints → Unifi DNS
  - Terraform manages DNSEndpoints via kubernetes provider for parity
  - `coredns` forwards `edgard.org` to Unifi (192.168.1.1)
- **Storage**: `local-fast` (default, `/mnt/spool/appdata`) and `local-bulk` (`/mnt/dpool`).
- **Commands**: `task lint`, `task argo:sync app=x`, `task argo:pf`, `task tf:apply`.

## Bitwarden Secret Keys

Secrets must exist with these exact keys:
- **Bootstrap**: `dockerhub_username`, `dockerhub_token`
- **Argo**: `argocd_admin_password_hash`, `argocd_admin_password_mtime`, `argocd_repo_username`, `argocd_repo_password`
- **Platform**: `cert_manager_cloudflare_api_token`, `external_dns_unifi_api_key`, `kopia_repository_password`, `kopia_server_username`, `kopia_server_password`, `tailscale_auth_key`
- **Media**: `qbittorrent_server_cities`, `qbittorrent_wireguard_addresses`, `qbittorrent_wireguard_private_key`, `unpackerr_radarr_api_key`, `unpackerr_sonarr_api_key`
- **Selfhosted**: `changedetection_api_key`, `changedetection_notification_url`, `karakeep_nextauth_secret`, `karakeep_meili_master_key`, `karakeep_openrouter_api_key`, `paperless_secret_key`, `paperless_admin_user`, `paperless_admin_password`, `paperless_api_token`, `paperless_ai_openai_api_key`, `paperless_ai_jwt_secret`, `gatus_telegram_token`, `gatus_telegram_chatid`, `security_notifier_telegram_token`, `security_notifier_telegram_chatid`

**Note**: Tailscale OAuth credentials (`TAILSCALE_OAUTH_CLIENT_ID`, `TAILSCALE_OAUTH_CLIENT_SECRET`) are local-only for Terraform, not in Bitwarden.

## Homelab Controller

- **Technology**: Python 3.14 + Kopf framework. Wave `-3`.
- **Features**:
  1. **GatusConfig CRD**: Discovers Services labeled `gatus.edgard.org/enabled=true`, generates Gatus config. Matches workload probes. Outputs `gatus-generated-config` ConfigMap. Reconciles on changes + every 120s.
  2. **Falco Integration**: Receives alerts via `/notify/falco` webhook. Sends daily Telegram digest (8:00 AM). Stores at `/data/alerts/pending.json`.
- **RBAC**: ClusterRole for CRDs (read), ConfigMaps (write), Services/Deployments (read).

### Debugging Homelab Controller

```bash
kubectl -n selfhosted get gatusconfig gatus-config -o yaml
kubectl -n platform-system logs -l app.kubernetes.io/name=homelab-controller -f
kubectl -n selfhosted annotate gatusconfig gatus-config force-sync=$(date +%s) --overwrite
kubectl -n platform-system port-forward svc/homelab-controller 8080:80
curl -X POST http://localhost:8080/notify/falco -H 'Content-Type: application/json' -d '{"rule":"test","priority":"INFO"}'
```

## Kopia Backup Server

- **Technology**: Kopia 0.18.2. Wave `-3`. TLS via gateway wildcard cert.
- **Repository**: 5Ti local-bulk PVC at `/repository/kopia`.
- **Schedule**: Daily 03:00. Retention: 7 daily, 4 weekly, 12 monthly, 3 yearly.
- **Access**: `https://kopia.edgard.org:51515` (VPN-only, Multus LAN IP 192.168.1.244).
- **Backup Source**: `/mnt/spool/appdata` hostPath (read-write).
- **Client Setup**: `kopia repository connect server --url=https://kopia.edgard.org`
- **User Management**: Admin credentials for all clients (VPN-only, trusted).
- **Monitoring**: Auto-discovered via `gatus.edgard.org/enabled: "true"` label.
- **Init**: InitContainer auto-creates repository, configures policies (idempotent).

## Resource Naming Conventions

Files must match `metadata.name`.

| Resource Type | Pattern | Example |
|---------------|---------|---------|
| Manifest File | `{app}-{descriptor}.{kind}.yaml` | `gateway-credentials.externalsecret.yaml` |
| ExternalSecret | `{app}-[{descriptor}-]credentials` | `gateway-credentials` |
| TLS Secret | `{app}-{descriptor}-tls` | `gateway-wildcard-tls` |
| Certificate | `{app}-{descriptor}` | `gateway-wildcard` |
| Generated CM | `{app}-generated-config` | `gatus-generated-config` (do not edit) |
| Gateway | `gateway` | `gateway` |
| Issuer | `{app}-issuer-{env}` | `gateway-issuer-production` |
| HTTPRoute | `{app}` | `homepage` |
| CRD | `{plural}.{group}` | `gatusconfigs.homelab.edgard.org` |
| ServiceAccount | `{app}` | `external-dns` |

## App-Template House Style (v4.5.0)

Applies to apps using `ghcr.io/bjw-s-labs/helm/app-template`.

- **Structure**: `defaultPodOptions` → `controllers` → `rbac` → `service` → `route` → `persistence`.
- **Controllers**: Use `controllers.main` and `containers.app`. Prefer `replicas: 1` / `strategy: Recreate`.
- **Persistence**: Main data = `persistence.data`. Config = `persistence.config`.
- **Probes**: Simplified structure (`probes: { startup: { enabled: true }, ... }`).

### Security Contexts

- **Pod Baseline**: `defaultPodOptions.securityContext: { fsGroupChangePolicy: OnRootMismatch }`.
- **Pod Non-Root (Preferred)**: Add `fsGroup: 568`, `runAsGroup: 568`, `runAsUser: 568`, `runAsNonRoot: true`.
- **Container Baseline**: `securityContext: { allowPrivilegeEscalation: false }`.
- **Container Strict**: Add `capabilities: { drop: ["ALL"] }`.
- **Exceptions**: Bind <1024 (`NET_BIND_SERVICE`), VPN (`NET_ADMIN`), Hardware (`privileged: true`).

### Resource Limits Policy

- **All apps run unlimited**: `resources: { limits: null, requests: null }` (renders as `resources: {}`).
- **Rationale**: VPN-only access eliminates DDoS risk.
- **Gateway**: Istio gateway uses default resources (managed by Gateway API).

### Compliance Status

- **Fully Compliant**: home-assistant, mosquitto, bazarr, flaresolverr, jellyfin, prowlarr, radarr, recyclarr, sonarr, unpackerr, homelab-controller, atuin, changedetection, echo, gatus, homepage, karakeep, paperless.
- **Exceptions**:
  - `zigbee2mqtt`: privileged (USB)
  - `qbittorrent`: `NET_ADMIN` (VPN)
  - `kopia`: Root required (hostPath)
  - `tailscale-subnet-router`: `NET_ADMIN`/`NET_RAW`, `hostNetwork: true` (LAN bridge)
