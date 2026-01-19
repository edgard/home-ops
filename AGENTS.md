# AI Agent Instructions
<!-- When editing: Keep this file under 100 lines. Be concise. -->
## Project Overview
GitOps-managed Talos Kubernetes homelab on TrueNAS. Local network access only. Single-node cluster. All changes via PR.
**Tech Stack**: Talos Linux • Kubernetes • Argo CD • Istio Gateway API • External Secrets (Bitwarden) • Helm • Terraform (Cloudflare)
**Key Dirs**: `apps/<group>/<app>/` (config.yaml, values.yaml, manifests/) • `argocd/` (root.app.yaml, appsets/) • `bootstrap/` (platform bootstrap) • `terraform/`
## Architecture
Talos on TrueNAS, local network access (192.168.1.0/24), Istio Gateway API ingress with bridge interface, split DNS (Cloudflare public/Unifi internal), Bitwarden secrets, NFS CSI for storage.
## Critical Rules
### Code Standards
- **YAML**: 2 spaces, no tabs. Run `task lint` before commits. Start files with `---`
- **File naming**: `{app}-{descriptor}.{kind}.yaml` (e.g., `gatus-credentials.externalsecret.yaml`)
- **Helm**: Use `ghcr.io/bjw-s-labs/helm/app-template` v4.5.0. Structure: `defaultPodOptions` → `controllers` → `service` → `route` → `persistence`
- **Resources**: All apps run unlimited (`resources: {}`). Local network only = no DDoS risk
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
- **Exceptions**: Bind <1024 (`NET_BIND_SERVICE`), Hardware (`privileged: true`), s6-overlay images (must run as root)
### Security + Permissions
- **Defaults**: Non-root `1000:1000`, `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`
- **s6-overlay**: Run pod as root and add `SETUID/SETGID` so it can drop to mapped users
- **Mappings**: LSIO uses `PUID/PGID=1000`, Paperless `USERMAP_UID/GID=1000`, Karakeep has no user mapping (root)
- **PVCs**: Ownership should match the app process UID/GID
### Argo CD Sync Waves
`-4` CRDs → `-3` Controllers/DNS → `-2` Mesh → `-1` k8tz → `0` Apps

### Storage
- `nfs-fast` (default): `192.168.1.254:/mnt/spool/appdata`
- `nfs-media`: `192.168.1.254:/mnt/dpool/media`
- `nfs-restic`: `192.168.1.254:/mnt/dpool/restic`

### DNS & Networking
- **Ingress**: Istio Gateway (`gateway` in platform-system) with `*.edgard.org` TLS cert
- **Public DNS**: Terraform manages Cloudflare (`terraform/cloudflare/dns.tf`)
- **Internal DNS**: external-dns syncs HTTPRoutes to Unifi (192.168.1.1), coredns forwards `edgard.org` to Unifi
- **Split-DNS**: DNSEndpoints in `terraform/cloudflare/dnsendpoints.tf` keep Terraform and external-dns in sync
## External Dependencies
- **Bitwarden**: Org `b4b5...`, Proj `1684...`. Requires `BWS_ACCESS_TOKEN` env var
- **Cloudflare**: DNS and ACME TLS. Terraform-managed
- **Unifi**: Internal DNS (192.168.1.1). Receives DNSEndpoint updates from external-dns
- **TrueNAS**: Storage host. Paths: `/mnt/spool/appdata`, `/mnt/dpool/media`, `/mnt/dpool/restic`

## Bitwarden Secrets (must match exactly)
- **Bootstrap**: `dockerhub_username`, `dockerhub_token`
- **Argo**: `argocd_admin_password_hash`, `argocd_admin_password_mtime`, `argocd_repo_username`, `argocd_repo_password`
- **Platform**: `cert_manager_cloudflare_api_token`, `external_dns_unifi_api_key`, `restic_server_password`, `telegram_bot_token`, `telegram_chat_id`
- **Home Automation**: `homebridge_username`, `homebridge_password`
- **Media**: `plex_claim`, `plextraktsync_plex_token`, `plextraktsync_plex_username`, `plextraktsync_trakt_username`, `qbittorrent_server_cities`, `qbittorrent_wireguard_addresses`, `qbittorrent_wireguard_private_key`, `unpackerr_radarr_api_key`, `unpackerr_sonarr_api_key`
- **Selfhosted**: `changedetection_api_key`, `karakeep_nextauth_secret`, `karakeep_meili_master_key`, `mcp_github_token`, `mcp_n8n_api_key`, `mcp_context7_api_key`, `n8n_encryption_key`, `openrouter_api_key`, `paperless_secret_key`, `paperless_admin_user`, `paperless_admin_password`, `paperless_api_token`

## Bootstrap Flow
`task cluster:create` → `task platform:create` → Argo CD syncs apps

## Common Tasks
```bash
task lint                          # Format & lint YAML
task cluster:create                # Install and bootstrap Talos + platform
task cluster:destroy               # Destroy platform and reset Talos node
task talos:gen                     # Generate Talos config
task talos:apply                   # Apply Talos config
task talos:bootstrap               # Bootstrap Talos control plane
task platform:create               # Install platform components
task platform:destroy              # Uninstall platform components
task argo:sync                     # Sync all Argo apps
task argo:sync app=<name>          # Sync specific app
task tf:plan                       # Terraform plan
task tf:apply                      # Terraform apply
```

## Homelab Controller
Python 3.14.2 + Kopf. Wave `-3`. Reconciles **GatusConfig CRD**: discovers Services with label `gatus.edgard.org/enabled=true`, generates Gatus config matching workload probes, outputs to `gatus-generated-config` ConfigMap.

## Key Constraints
- **Local Network Only**: All services accessible only from 192.168.1.0/24. No public or VPN access
- **Single-Node**: No HA. Use `Recreate` strategy
- **NFS Exports**: Requires `/mnt/spool/appdata`, `/mnt/dpool/media`, `/mnt/dpool/restic` on TrueNAS host
- **PR Workflow**: All changes must go through pull requests. Never commit directly to master

## Resource Naming
| Type | Pattern | Example |
|------|---------|---------|
| Manifest File | `{app}-{descriptor}.{kind}.yaml` | `gateway-credentials.externalsecret.yaml` |
| ExternalSecret | `{app}-[{descriptor}-]credentials` | `gateway-credentials` |
| ConfigMap | `{app}-{descriptor}` | `gatus-generated-config` |
| HTTPRoute | `{app}` | `homepage` |
| Certificate | `{app}-{descriptor}` | `gateway-wildcard` |

## App Categories
Platform: cert-manager, external-dns, external-secrets, gateway-api, homelab-controller, istio, reloader. Home Automation: homebridge, matterbridge, mosquitto, scrypted, zigbee2mqtt. Media: plex, radarr, sonarr, bazarr, prowlarr, qbittorrent, recyclarr, unpackerr. Selfhosted: atuin, changedetection, gatus, homepage, karakeep, n8n, paperless, restic.
