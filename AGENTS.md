# AI Agent Instructions
<!-- When editing: Keep this file under 100 lines. Be concise. -->

## Project Overview
GitOps-managed K3s homelab on TrueNAS (k3d). VPN-only access. Single-node cluster. Direct commits to master.

**Tech Stack**: K3s v1.33.6 • Argo CD • Istio Gateway API • External Secrets (Bitwarden) • Helm • Terraform (Cloudflare/Tailscale)

**Key Dirs**: `apps/<group>/<app>/` (config.yaml, values.yaml, manifests/) • `argocd/` (root.app.yaml, appsets/) • `bootstrap/` (k3d setup) • `terraform/`

## Critical Rules

### Code Standards
- **YAML**: 2 spaces, no tabs. Run `task lint` before commits. Start files with `---`
- **File naming**: `{app}-{descriptor}.{kind}.yaml` (e.g., `gatus-credentials.externalsecret.yaml`)
- **Helm**: Use `ghcr.io/bjw-s-labs/helm/app-template` v4.5.0. Structure: `defaultPodOptions` → `controllers` → `service` → `route` → `persistence`
- **Resources**: All apps run unlimited (`resources: {}`). VPN-only = no DDoS risk
- **Security**: Non-root by default, `fsGroup: 1000`, drop all capabilities where possible
- **Deployment**: `replicas: 1`, `strategy: Recreate` (single-node cluster)

### Manifest Structure
- **Start with**: `---` on line 1
- **Field order**: `apiVersion` → `kind` → `metadata` → `spec`
- **Metadata order**: `name` → `namespace` → `labels` → `annotations`
- **ExternalSecret**: `refreshInterval` → `secretStoreRef` (name before kind) → `target` → `data`

### Security Contexts (App-Template)
- **Pod baseline**: `fsGroupChangePolicy: OnRootMismatch`
- **Pod non-root**: Add `fsGroup: 1000`, `runAsGroup: 1000`, `runAsUser: 1000`, `runAsNonRoot: true`
- **Container baseline**: `allowPrivilegeEscalation: false`
- **Container strict**: Add `capabilities: { drop: ["ALL"] }`
- **Exceptions**: Bind <1024 (`NET_BIND_SERVICE`), VPN (`NET_ADMIN`), Hardware (`privileged: true`), s6-overlay images (must run as root)

### Argo CD Sync Waves
`-4` CRDs → `-3` Controllers/DNS/VPN → `-2` Mesh → `-1` k8tz → `0` Apps

### Storage
- `local-fast` (default): `/mnt/spool/appdata` (SSD)
- `local-bulk`: `/mnt/dpool` (HDD, for media)

### DNS & Networking
- **Ingress**: Istio Gateway (`gateway` in platform-system) with `*.edgard.org` TLS cert
- **Public DNS**: Terraform manages Cloudflare (`terraform/cloudflare/dns.tf`)
- **Internal DNS**: external-dns syncs HTTPRoutes to Unifi (192.168.1.1), coredns forwards `edgard.org` to Unifi
- **Split-DNS**: DNSEndpoints in `terraform/cloudflare/dnsendpoints.tf` keep Terraform and external-dns in sync

## External Dependencies
- **Bitwarden**: Org `b4b5...`, Proj `1684...`. Requires `BWS_ACCESS_TOKEN` env var
- **Cloudflare**: DNS and ACME TLS. Terraform-managed
- **Tailscale**: VPN access. OAuth creds (`TAILSCALE_OAUTH_CLIENT_ID`, `TAILSCALE_OAUTH_CLIENT_SECRET`) local-only, auth key in Bitwarden
- **Unifi**: Internal DNS (192.168.1.1). Receives DNSEndpoint updates from external-dns
- **TrueNAS**: Docker host via SSH. Requires `DOCKER_HOST` env var (e.g., `ssh://user@host`). Paths: `/mnt/spool/appdata`, `/mnt/dpool/media`, `/mnt/dpool/kopia-repo`

## Bitwarden Secrets (must match exactly)
- **Bootstrap**: `dockerhub_username`, `dockerhub_token`
- **Argo**: `argocd_admin_password_hash`, `argocd_admin_password_mtime`, `argocd_repo_username`, `argocd_repo_password`
- **Platform**: `cert_manager_cloudflare_api_token`, `external_dns_unifi_api_key`, `kopia_repository_password`, `kopia_server_username`, `kopia_server_password`, `tailscale_auth_key`
- **Home Automation**: `nodered_credential_secret`
- **Media**: `plex_claim`, `plextraktsync_plex_token`, `plextraktsync_plex_username`, `plextraktsync_trakt_username`, `qbittorrent_server_cities`, `qbittorrent_wireguard_addresses`, `qbittorrent_wireguard_private_key`, `unpackerr_radarr_api_key`, `unpackerr_sonarr_api_key`
- **Selfhosted**: `changedetection_api_key`, `changedetection_notification_url`, `gatus_telegram_token`, `gatus_telegram_chat_id`, `karakeep_nextauth_secret`, `karakeep_meili_master_key`, `karakeep_openrouter_api_key`, `paperless_secret_key`, `paperless_admin_user`, `paperless_admin_password`, `paperless_api_token`, `paperless_ai_openai_api_key`, `paperless_ai_jwt_secret`

## Bootstrap Flow
1. `task bootstrap:create` creates k3d cluster on remote TrueNAS via SSH (`DOCKER_HOST=ssh://user@host`)
2. Requires `BWS_ACCESS_TOKEN` env var
3. Helmfile installs: local-path-provisioner, multus, cert-manager, external-secrets, Argo CD
4. Argo CD syncs all apps via ApplicationSet

## Common Tasks
```bash
task lint                          # Format & lint YAML
task bootstrap:create              # Create cluster (needs DOCKER_HOST, BWS_ACCESS_TOKEN)
task bootstrap:destroy             # Destroy cluster
task argo:sync                     # Sync all Argo apps
task argo:sync app=<name>          # Sync specific app
task tf:plan                       # Terraform plan
task tf:apply                      # Terraform apply
```

## Homelab Controller
Python 3.14.2 + Kopf. Wave `-3`. Reconciles **GatusConfig CRD**: discovers Services with label `gatus.edgard.org/enabled=true`, generates Gatus config matching workload probes, outputs to `gatus-generated-config` ConfigMap.

## Key Constraints
- **VPN-Only**: All services require Tailscale. No public exposure
- **Single-Node**: No HA. Use `Recreate` strategy
- **Host Mounts**: Requires `/mnt/spool/appdata`, `/mnt/dpool/media`, `/mnt/dpool/kopia-repo` on TrueNAS host
- **Direct to Master**: No PRs. Commit directly to master branch

## Resource Naming
| Type | Pattern | Example |
|------|---------|---------|
| Manifest File | `{app}-{descriptor}.{kind}.yaml` | `gateway-credentials.externalsecret.yaml` |
| ExternalSecret | `{app}-[{descriptor}-]credentials` | `gateway-credentials` |
| ConfigMap | `{app}-{descriptor}` | `gatus-generated-config` |
| HTTPRoute | `{app}` | `homepage` |
| Certificate | `{app}-{descriptor}` | `gateway-wildcard` |

## App Categories
- **Platform**: cert-manager, external-dns, external-secrets, gateway-api, homelab-controller, istio, kopia, reloader, tailscale
- **Home Automation**: home-assistant, matterbridge, mosquitto, nodered, scrypted, zigbee2mqtt
- **Media**: plex, radarr, sonarr, bazarr, prowlarr, qbittorrent, recyclarr, unpackerr
- **Selfhosted**: atuin, changedetection, gatus, homepage, karakeep, paperless
