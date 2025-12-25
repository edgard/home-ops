# Project Context

## Purpose
Home Operations (home-ops) is a GitOps-managed Kubernetes homelab infrastructure running on K3s in TrueNAS containers. The project automates deployment of home automation, media management, and self-hosted services with a focus on security, reproducibility, and VPN-only access.

## Tech Stack
- **Container Orchestration**: Kubernetes (K3s v1.33.6+k3s1)
- **GitOps**: Argo CD with ApplicationSets
- **Infrastructure as Code**: Terraform (Cloudflare, Tailscale)
- **Package Management**: Helm, Helmfile
- **Custom Controllers**: Python 3.14 + Kopf framework
- **Service Mesh**: Istio (Gateway API)
- **Secrets Management**: External Secrets Operator + Bitwarden
- **Storage**: local-path-provisioner (fast/bulk tiers)
- **Backup**: Kopia server
- **Monitoring**: Gatus
- **VPN**: Tailscale subnet router

## Project Conventions

### Code Style
- **YAML Formatting**: Use `.yamlfmt` and `.yamllint` configs. Run `task lint` before commits.
- **File Naming**: Kebab-case. Manifests follow `{app}-{descriptor}.{kind}.yaml` pattern.
- **Indentation**: 2 spaces. No tabs. Keep files ASCII-compatible.

### Architecture Patterns
- **GitOps Model**: All cluster state declared in Git. Argo CD syncs from main branch.
- **App Structure**: `apps/<group>/<app>/` contains `config.yaml`, `values.yaml`, and `manifests/` directory.
- **Sync Waves**: Ordered deployment via Argo CD sync-wave annotations (-4 to 0).
- **Security**: VPN-only access (no public exposure). Non-root containers by default. Secrets from Bitwarden only.
- **Helm Pattern**: Prefer `ghcr.io/bjw-s-labs/helm/app-template` v4.5.0 for consistent app structure.
- **Resource Limits**: All apps run unlimited (`resources: {}`). VPN-only eliminates DDoS risk.

### Testing Strategy
- Pre-commit linting via `task lint` (yamlfmt, yamllint, prettier).

### Git Workflow
- **Default Branch**: `master`
- **Commit Strategy**: Direct commits to master (personal repo)
- **Merge Strategy**: Fast-forward only for master/main branches
- **Commit Conventions**: Clear, concise commit messages focusing on what changed and why
- **Aliases**: Use short git aliases (st, co, ci, br, df, dc, pr, lg)
- **Fetch Behavior**: Auto-prune deleted remote branches
- **Rebase**: Auto-squash enabled for fixup commits

## Domain Context

### Kubernetes Homelab
- **Cluster Type**: k3d (K3s in Docker, single-node, running on remote TrueNAS Docker host via SSH)
- **Bootstrap**: `bootstrap-k3d.sh` handles k3d cluster creation, K3s configuration, and platform setup via `helmfile.yaml.gotmpl`
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
- **Container Security**: Non-root by default, drop all capabilities, read-only root filesystem where possible.

### App Categories
- **Home Automation**: home-assistant, matterbridge, mosquitto, nodered, scrypted, zigbee2mqtt
- **Media**: Plex, Plextraktsync, Radarr, Sonarr, Bazarr, Prowlarr, qBittorrent (via Gluetun VPN), Recyclarr, Unpackerr
- **Self-hosted**: Atuin, Changedetection, Gatus, Homepage, Karakeep, Paperless-ngx
- **Platform**: cert-manager, external-dns, external-secrets, Gateway API, homelab-controller, Istio, Kopia, Multus, Reloader, Tailscale

## Important Constraints
- **VPN-Only Access**: All services require Tailscale connection. No public internet exposure.
- **Single-Node Cluster**: K3s-based. Limited HA options. Use `Recreate` deployment strategy.
- **Host Dependencies**: Requires `/mnt/spool` and `/mnt/dpool` bind mounts in K3s container.
- **TrueNAS Container**: Requires TrueNAS Scale 25.04+ with Container API access.
- **Secret Keys**: Bitwarden secrets must match exact keys listed in AGENTS.md.
- **Resource Philosophy**: No limits/requests set. Trust VPN-protected environment.

## External Dependencies
- **Bitwarden Secrets Manager**: Secret storage (Org `b4b5...`, Proj `1684...`). Requires `BWS_ACCESS_TOKEN` env var.
- **Cloudflare**: DNS and ACME TLS challenge. Terraform-managed.
- **Tailscale**: VPN access layer. OAuth credentials for Terraform, auth key in Bitwarden for subnet router.
- **Unifi Network**: Internal DNS server (192.168.1.1). Receives DNSEndpoint updates from external-dns.
- **TrueNAS Scale**: Docker host accessed via SSH. Requires `DOCKER_HOST_SSH` env var for bootstrap.
- **Telegram**: Alert delivery for Gatus (via homelab-controller).

---

# Operational Reference

This section contains runtime operational details for day-to-day maintenance.

## Repo Layout & Bootstrap

- **`bootstrap/`**: k3d cluster config, `bootstrap-k3d.sh` (connects to remote Docker via SSH, creates k3d cluster), and `helmfile.yaml.gotmpl`.
  - **Process**: `task bootstrap:create` creates k3d cluster on remote TrueNAS Docker host, configures kubeconfig, creates `bitwarden-credentials` (from `BWS_ACCESS_TOKEN`), and runs helmfile.
  - **Helmfile**: Installs local-path-provisioner (demotes standard SC), cert-manager, ESO (wait for CM), Argo CD.
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
- **Home Automation**: `nodered_credential_secret`
- **Media**: `plex_claim`, `plextraktsync_plex_token`, `plextraktsync_plex_username`, `plextraktsync_trakt_username`, `qbittorrent_server_cities`, `qbittorrent_wireguard_addresses`, `qbittorrent_wireguard_private_key`, `unpackerr_radarr_api_key`, `unpackerr_sonarr_api_key`
- **Selfhosted**: `changedetection_api_key`, `changedetection_notification_url`, `karakeep_nextauth_secret`, `karakeep_meili_master_key`, `karakeep_openrouter_api_key`, `paperless_secret_key`, `paperless_admin_user`, `paperless_admin_password`, `paperless_api_token`, `paperless_ai_openai_api_key`, `paperless_ai_jwt_secret`, `gatus_telegram_token`, `gatus_telegram_chatid`, `security_notifier_telegram_token`, `security_notifier_telegram_chatid`

**Note**: Tailscale OAuth credentials (`TAILSCALE_OAUTH_CLIENT_ID`, `TAILSCALE_OAUTH_CLIENT_SECRET`) are local-only for Terraform, not in Bitwarden.

## Homelab Controller

- **Technology**: Python 3.14 + Kopf framework. Wave `-3`.
- **Features**:
  1. **GatusConfig CRD**: Discovers Services labeled `gatus.edgard.org/enabled=true`, generates Gatus config. Matches workload probes. Outputs `gatus-generated-config` ConfigMap. Reconciles on changes + every 120s.
  2. **Falco Integration**: Receives alerts via `/notify/falco` webhook. Sends daily Telegram digest (8:00 AM). Stores at `/data/alerts/pending.json`.
- **RBAC**: ClusterRole for CRDs (read), ConfigMaps (write), Services/Deployments (read).

## Kubernetes Manifest Standards

All Kubernetes manifests in the project follow consistent patterns for naming, structure, and formatting to ensure maintainability and predictability.

### File Naming Convention

Manifest files MUST follow the pattern: `{app}-{descriptor}.{kind}.yaml`

- `{app}`: Application name in kebab-case
- `{descriptor}`: Optional descriptor providing context (e.g., "credentials", "config", "wildcard")
- `{kind}`: Kubernetes resource kind in lowercase (e.g., "externalsecret", "configmap", "certificate")

**Exemptions**: Vendor-provided CRD files (e.g., Gateway API CRDs) may retain original filenames and multi-document structure.

### Resource Naming Patterns

Files must match `metadata.name`.

| Resource Type | Pattern | Example |
|---------------|---------|---------|
| Manifest File | `{app}-{descriptor}.{kind}.yaml` | `gateway-credentials.externalsecret.yaml` |
| ExternalSecret | `{app}-[{descriptor}-]credentials` | `gateway-credentials` |
| ConfigMap | `{app}-{descriptor}` | `homelab-controller-controller` |
| TLS Secret | `{app}-{descriptor}-tls` | `gateway-wildcard-tls` |
| Certificate | `{app}-{descriptor}` | `gateway-wildcard` |
| Issuer | `{app}-issuer-{env}` | `gateway-issuer-production` |
| StorageClass | `{name}` | `local-fast`, `local-bulk` |
| CRD | `{plural}.{group}` | `gatusconfigs.homelab.edgard.org` |
| Gateway | `gateway` | `gateway` |
| HTTPRoute | `{app}` | `homepage` |
| ServiceAccount | `{app}` | `external-dns` |
| ClusterRole | `{app}[-{descriptor}]` | `k8tz-wait-cert-manager` |
| Job | `{app}-{descriptor}` | `k8tz-wait-cert-manager` |
| Generated CM | `{app}-generated-config` | `gatus-generated-config` (do not edit) |

### Manifest Structure Standards

**Document Format**:
- All manifests MUST start with `---` document separator on line 1
- Single resource per file (except vendor-provided multi-document CRDs)
- UTF-8 encoding, 2-space indentation, no tabs

**Top-level Field Order**:
1. `apiVersion`
2. `kind`
3. `metadata`
4. `spec` (or `data` for ConfigMaps/Secrets)
5. Additional fields as needed

**Metadata Field Order**:
1. `name`
2. `namespace` (if namespaced resource)
3. `labels` (if present)
4. `annotations` (if present)
5. Additional metadata fields

**Spec Field Ordering Examples**:
- **ExternalSecret**: `refreshInterval`, `secretStoreRef` (with `name` before `kind`), `target`, `data`
- **ClusterRoleBinding**: `roleRef` before `subjects`
- **Certificate**: `secretName`, `issuerRef`, `dnsNames`, additional fields

**Formatting Requirements**:
- Must pass `task lint` (yamlfmt + yamllint)
- Indentation: 2 spaces (no tabs)
- Line endings: LF (Unix-style)
- Keep files ASCII-compatible where possible

## App-Template House Style (v4.5.0)

Applies to apps using `ghcr.io/bjw-s-labs/helm/app-template`.

- **Structure**: `defaultPodOptions` → `controllers` → `rbac` → `service` → `route` → `persistence`.
- **Controllers**: Use `controllers.main` and `containers.app`. Prefer `replicas: 1` / `strategy: Recreate`.
- **Persistence**: Main data = `persistence.data`. Config = `persistence.config`.
- **Probes**: Simplified structure (`probes: { startup: { enabled: true }, ... }`).

### Security Contexts

- **Pod Baseline**: `defaultPodOptions.securityContext: { fsGroupChangePolicy: OnRootMismatch }`.
- **Pod Non-Root (Preferred)**: Add `fsGroup: 1000`, `runAsGroup: 1000`, `runAsUser: 1000`, `runAsNonRoot: true`.
- **Container Baseline**: `securityContext: { allowPrivilegeEscalation: false }`.
- **Container Strict**: Add `capabilities: { drop: ["ALL"] }`.
- **Exceptions**: Bind <1024 (`NET_BIND_SERVICE`), VPN (`NET_ADMIN`), Hardware (`privileged: true`).

### Resource Limits Policy

- **All apps run unlimited**: `resources: { limits: null, requests: null }` (renders as `resources: {}`).
- **Rationale**: VPN-only access eliminates DDoS risk.
- **Gateway**: Istio gateway uses default resources (managed by Gateway API).
