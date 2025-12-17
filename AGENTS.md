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
- **`terraform/`**: Cloudflare config (B2 backend).

## Argo CD & Apps
- **Sync Waves**: `-5` System/CRDs, `-4` Controllers/DNS, `-3` Mesh/Authn, `-2` Edge, `-1` k8tz, `0` Apps.
- **Mechanics**: ServerSideApply (`SSA`) enabled globally. Progressive syncs/rollouts disabled.
- **Istio/Ingress**: Gateway API used (`gateway-external`, `gateway-internal`). `oauth2-proxy` handles OIDC (headers only, no access tokens upstream).
- **DNS**: `coredns` overrides `edgard.org` to Unifi (192.168.1.1) and `id.edgard.org` to Internal Gateway (192.168.1.241).
- **Storage**: `local-fast` (default, `/mnt/spool/appdata`) and `local-bulk` (`/mnt/dpool`).
- **Commands**: `task lint` (format), `task argo:sync app=x`, `task argo:pf` (UI), `task tf:apply`.

## Bitwarden Secret Keys
Secrets must exist in Bitwarden with these exact keys:
- **Bootstrap**: `dockerhub_username`, `dockerhub_token`
- **Argo**: `argocd_admin_password_hash`, `argocd_admin_password_mtime`, `argocd_repo_username`, `argocd_repo_password`
- **Platform**: `cert_manager_cloudflare_api_token`, `cloudflared_tunnel_token`, `external_dns_cloudflare_api_token`, `external_dns_unifi_api_key`, `dex_admin_password_hash`, `oauth2_proxy_client_secret`, `oauth2_proxy_cookie_secret`, `restic_password`
- **Media**: `qbittorrent_server_cities`, `qbittorrent_wireguard_addresses`, `qbittorrent_wireguard_private_key`, `unpackerr_radarr_api_key`, `unpackerr_sonarr_api_key`
- **Selfhosted**: `changedetection_api_key`, `changedetection_notification_url`, `karakeep_nextauth_secret`, `karakeep_meili_master_key`, `karakeep_openrouter_api_key`, `karakeep_api_key`, `paperless_secret_key`, `paperless_admin_user`, `paperless_admin_password`, `paperless_api_token`, `paperless_ai_openai_api_key`, `paperless_ai_jwt_secret`, `gatus_telegram_token`, `gatus_telegram_chatid`, `security_notifier_telegram_token`, `security_notifier_telegram_chatid`

## Resource Naming Conventions
Files must match `metadata.name`.

| Resource Type | Pattern | Example |
|---------------|---------|---------|
| Manifest File | `{app}-{descriptor}.{kind}.yaml` | `istio-credentials.externalsecret.yaml` |
| ExternalSecret | `{app}-credentials` | `restic-credentials` |
| TLS Secret | `{app}-{descriptor}-tls` | `gateway-wildcard-tls` |
| Generated CM | `{app}-generated-config` | `gatus-generated-config` (do not edit) |
| Gateway | `gateway-{scope}` | `gateway-external` |
| Issuer | `{app}-issuer-{env}` | `gateway-issuer-production` |
| HTTPRoute | `{app}-{purpose}` | `oauth2-proxy-auth-external` |
| CRD | `{plural}.{group}` | `gatusconfigs.homelab.edgard.org` |
| ServiceAccount | `{app}` | `external-dns-external` |

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

### Compliance Status
- **Fully Compliant**: home-assistant, mosquitto, bazarr, flaresolverr, jellyfin, prowlarr, radarr, recyclarr, sonarr, unpackerr, cloudflared, dex, homelab-controller, atuin, changedetection, echo, gatus, homepage.
- **Exceptions**:
  - `zigbee2mqtt`: privileged (USB).
  - `qbittorrent`: `NET_ADMIN` (VPN).
  - `restic`: Root required.
  - `karakeep`, `nginx`, `paperless`: Pending update to app-template security styles.
