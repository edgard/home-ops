# AI Maintainer Guide

- **Maintain this file.** Updates to automation, commands, or docs must update `AGENTS.md` in the same PR.
- **Safety.** Default to safe edits. No destructive git ops. No decrypted secrets in commits.
- **Search.** Use `rg --files`. Keep files ASCII.
- **Context.** Detailed procedures live here but try to keep under 100 lines; `README.md` is high-level.

## Repo Layout & Architecture
- **`bootstrap/`**: Kind config, `bootstrap_kind.py` (docker context/network plumbing), and `helmfile.yaml.gotmpl`.
  - **Process**: `task bootstrap:create` brings up Kind, patches kubeconfig, creates `bitwarden-credentials` (from `BWS_ACCESS_TOKEN`), and runs helmfile.
  - **Helmfile**: Installs local-path-provisioner (demotes standard SC), Multus, cert-manager, ESO (wait for CM), Argo CD.
  - **Secrets**: Stored in Bitwarden (Org `b4b5...`, Proj `1684...`). ESO fetches them via `external-secrets-sdk-server` (TLS via cert-manager).
- **`argocd/`**: `root.app.yaml` and `appsets/apps.appset.yaml` (ordered by sync-wave).
- **`apps/<group>/<app>/`**: `config.yaml` (chart source), `values.yaml`, `manifests/` (synced).
- **`terraform/`**: Cloudflare + Tailscale config (B2 backend).

## Argo CD & Apps
- **Sync Waves**: `-5` System/CRDs, `-4` Controllers/DNS/VPN, `-3` Mesh, `-1` k8tz, `0` Apps.
- **Mechanics**: ServerSideApply (`SSA`) enabled globally. Progressive syncs/rollouts disabled.
- **Istio/Ingress**: Gateway API used (`gateway`). All apps accessed via Tailscale VPN only.
- **DNS (Split)**: 
  - **Public (Cloudflare)**: Managed via Terraform (`terraform/cloudflare/dns.tf`).
  - **Internal (Unifi)**: `external-dns` syncs HTTPRoutes → 192.168.1.241 and DNSEndpoints → Unifi DNS.
  - **DNSEndpoints**: Terraform manages via kubernetes provider (`terraform/cloudflare/dnsendpoints.tf`) for split-DNS parity.
  - **Resolution**: `coredns` forwards `edgard.org` to Unifi (192.168.1.1). Tailscale split-DNS via Terraform.
- **Storage**: `local-fast` (default, `/mnt/spool/appdata`) and `local-bulk` (`/mnt/dpool`).
- **Commands**: `task lint` (format), `task argo:sync app=x`, `task argo:pf` (UI), `task tf:apply`.

## Tailscale VPN
- **Access Model**: VPN-only. Zero external exposure. All apps require Tailscale connection.
- **Subnet Router**: Advertises `192.168.1.0/24` to Tailscale network. Runs on worker node with `hostNetwork: true` and `NET_ADMIN`/`NET_RAW` capabilities. Uses auth key from Bitwarden.
- **Split-DNS**: Terraform configures `edgard.org` → Unifi DNS (192.168.1.1) for Tailscale clients.

## Bitwarden Secret Keys
Secrets must exist in Bitwarden with these exact keys:
- **Bootstrap**: `dockerhub_username`, `dockerhub_token`
- **Argo**: `argocd_admin_password_hash`, `argocd_admin_password_mtime`, `argocd_repo_username`, `argocd_repo_password`
- **Platform**: `cert_manager_cloudflare_api_token`, `external_dns_unifi_api_key`, `restic_password`, `tailscale_auth_key`
- **Media**: `qbittorrent_server_cities`, `qbittorrent_wireguard_addresses`, `qbittorrent_wireguard_private_key`, `unpackerr_radarr_api_key`, `unpackerr_sonarr_api_key`
- **Selfhosted**: `changedetection_api_key`, `changedetection_notification_url`, `karakeep_nextauth_secret`, `karakeep_meili_master_key`, `karakeep_openrouter_api_key`, `karakeep_api_key`, `paperless_secret_key`, `paperless_admin_user`, `paperless_admin_password`, `paperless_api_token`, `paperless_ai_openai_api_key`, `paperless_ai_jwt_secret`, `gatus_telegram_token`, `gatus_telegram_chatid`, `security_notifier_telegram_token`, `security_notifier_telegram_chatid`

**Note**: Tailscale OAuth credentials (`TAILSCALE_OAUTH_CLIENT_ID`, `TAILSCALE_OAUTH_CLIENT_SECRET`) are used locally by Terraform only, not stored in Bitwarden.

## Resource Naming Conventions
Files must match `metadata.name`.

| Resource Type | Pattern | Example |
|---------------|---------|---------|
| Manifest File | `{app}-{descriptor}.{kind}.yaml` | `gateway-credentials.externalsecret.yaml` |
| ExternalSecret | `{app}-[{descriptor}-]credentials` | `gateway-credentials`, `argocd-repo-credentials` |
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
- **Persistence**: Main data volume = `persistence.data`. Config mounts = `persistence.config`.
- **Probes**: Use simplified structure (`probes: { startup: { enabled: true }, ... }`).

### Security Contexts
- **Pod Baseline**: `defaultPodOptions.securityContext: { fsGroupChangePolicy: OnRootMismatch }`.
- **Pod Non-Root (Preferred)**: Add `fsGroup: 568`, `runAsGroup: 568`, `runAsUser: 568`, `runAsNonRoot: true`.
- **Container Baseline**: `securityContext: { allowPrivilegeEscalation: false }`.
- **Container Strict**: Add `capabilities: { drop: ["ALL"] }`.
- **Exceptions**: Bind <1024 (`NET_BIND_SERVICE`), VPN (`NET_ADMIN`), Hardware (`privileged: true`).

### Resource Limits Policy
- **All apps run unlimited**: `resources: { limits: null, requests: null }` (renders as `resources: {}`).
- **Rationale**: VPN-only access eliminates DDoS risk. No need for resource limits or requests.
- **Gateway**: Istio gateway uses default resources (managed by Gateway API).

### Compliance Status
- **Fully Compliant**: home-assistant, mosquitto, bazarr, flaresolverr, jellyfin, prowlarr, radarr, recyclarr, sonarr, unpackerr, homelab-controller, atuin, changedetection, echo, gatus, homepage, karakeep, paperless.
- **Exceptions**:
  - `zigbee2mqtt`: privileged (USB).
  - `qbittorrent`: `NET_ADMIN` (VPN).
  - `restic`: Root required.
  - `tailscale-subnet-router`: `NET_ADMIN`/`NET_RAW` (VPN routing), `hostNetwork: true` (LAN bridge).
