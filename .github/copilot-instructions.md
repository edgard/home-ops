# AI Maintainer Guide

- Keep this file current. Any change to automation, commands, dependencies, layout, or docs must update `.github/copilot-instructions.md` (and README.md) in the same commit/PR.
- Default to safe edits: never drop user changes, never commit decrypted secrets, avoid destructive git operations unless explicitly asked.
- Prefer `rg`/`rg --files` for search; stay ASCII unless a file already uses other characters.
- README is intentionally high level; keep detailed procedures and dependency notes here.

## Repo Layout
- `bootstrap/` – Kind cluster config and Kind cluster config (`cluster-config.yaml`), helmfile, and bootstrap script.
- `bootstrap/bootstrap_kind.py` – Kind cluster bring-up and host plumbing (docker context, macvlan attach, kubeconfig patch, Docker Hub auth). Bootstrap expects Docker context `kind-<cluster>` (default `kind-homelab`) to exist.
- `argocd/` – `root.app.yaml` bootstraps namespaces, projects, and the ApplicationSet (`appsets/apps.appset.yaml` with sync-wave ordering).
- `apps/<group>/<app>/` – `config.yaml` (chart source/version + optional rollout/sync), `values.yaml`, optional `manifests/` (always synced). Groups: argocd, kube-system, local-path-storage, platform-system, selfhosted, media, home-automation.
- `terraform/` – OpenTofu configs for Cloudflare using Backblaze B2 S3 backend (`shadowhausterraform/homelab/terraform.tfstate`); module in `terraform/cloudflare/`.

- Dependencies: docker, kind, kubectl, helm, python3 + PyYAML, go-task (`task`), prettier, yamlfmt, yamllint, tofu.
- Bootstrap uses `bootstrap/helmfile.yaml.gotmpl` (run via `task bootstrap:create` after the Kind bring-up) to install pre-Argo dependencies in order: local-path-provisioner (chart + manifests; postsync hook demotes Kind's default `standard` StorageClass if present so `local-fast` is the sole default), Multus, cert-manager, External Secrets Operator (with Bitwarden SDK server), and Argo CD. Helmfile waits for Jobs and cleans up on failure; hook scripts run under `bash` (for `pipefail`). A global `prepare` hook ensures namespaces needed by bootstrap-only manifests exist (`local-path-storage`, `media`, `platform-system`) and warms required images before any releases run. Chart refs/versions are read from each app’s `config.yaml`. The ESO release presync hook waits for cert-manager readiness, applies the `external-secrets-sdk-server-issuer` Issuer and `external-secrets-sdk-server-tls` Certificate manifests, and waits for the certificate to be ready, allowing cert-manager to generate the `bitwarden-tls-certs` Secret before the chart is installed. The ESO postsync hook applies the ClusterSecretStore (`external-secrets-store`) after CRDs are registered. The Argo release postsync applies the argocd-repo-credentials ExternalSecret, waits for it to sync, and finally applies the Argo root app. Argo later reconciles the same apps. Paths inside the helmfile are relative to `bootstrap/`.
- Create docker context `kind-homelab` (or `kind-<name>` from `cluster-config.yaml`) pointing at the host running dockerd; bootstrap fails if the context is missing.
- `task bootstrap:create` creates Kind, attaches workers to a macvlan network, patches kubeconfig endpoint (if remote), ensures platform-system namespace exists, creates the `bitwarden-credentials` Secret with BWS_ACCESS_TOKEN, then runs helmfile sync (prepare hook warms images, installs local-path-provisioner/Multus/cert-manager/ESO/Argo CD in sequence; ESO presync waits for cert-manager readiness and applies Issuer/Certificate for SDK server; ESO postsync creates ClusterSecretStore; argocd postsync applies argocd-repo-credentials ExternalSecret and waits for it to sync before applying root app).
- Warmup: `bootstrap/helmfile.yaml.gotmpl` creates short-lived pods in `kube-system` to pre-pull `docker.io/library/busybox:stable` and `quay.io/k8tz/k8tz:<version>` (version derived from `apps/kube-system/k8tz/config.yaml`), then deletes them.
- Secrets management: All secrets are stored in Bitwarden Secrets Manager (organizationID `b4b5d72b-b543-40b5-a09f-b3b501401fb1`, projectID `16848a5f-8d25-4560-af64-b3b5014052e7`). Bootstrap requires `BWS_ACCESS_TOKEN` env var. The ClusterSecretStore (`external-secrets-store`) references the SDK server at `https://bitwarden-sdk-server.platform-system.svc.cluster.local:9998`. All app secrets are fetched by ExternalSecrets post-bootstrap. The SDK server certificate is managed by cert-manager via `external-secrets-sdk-server-issuer` Issuer and `external-secrets-sdk-server-tls` Certificate (90-day validity, 15-day renewal window, sync-wave -4). Optional global Docker Hub auth: store `dockerhub_username` and `dockerhub_token` in Bitwarden Secrets Manager. Bootstrap reads them via BWS CLI (`bitwarden/bws:1.0.0` container running `secret list` command to find secrets by name), writes a fresh kubelet `/var/lib/kubelet/config.json` on every node with only the Docker Hub auth entry, and restarts kubelet. No env/config overrides are supported.
- Destroy/recreate: `task bootstrap:destroy` / `task bootstrap:recreate`.
- Env overrides honored by bootstrap: `MULTUS_PARENT_IFACE`, `MULTUS_PARENT_SUBNET`, `MULTUS_PARENT_GATEWAY`, `MULTUS_PARENT_IP_RANGE` (document when used).

### Bitwarden Secret Reference
All secrets must exist in Bitwarden Secrets Manager with these exact key names:
- **Bootstrap**: `dockerhub_username`, `dockerhub_token` (optional)
- **Argo CD**: `argocd_admin_password_hash`, `argocd_admin_password_mtime`, `argocd_repo_username`, `argocd_repo_password`
- **Platform**: `cert_manager_cloudflare_api_token`, `cloudflared_tunnel_token`, `external_dns_cloudflare_api_token`, `external_dns_unifi_api_key`, `dex_admin_password_hash`, `oauth2_proxy_client_secret`, `oauth2_proxy_cookie_secret`, `restic_password`
- **Media**: `qbittorrent_server_cities`, `qbittorrent_wireguard_addresses`, `qbittorrent_wireguard_private_key`, `unpackerr_radarr_api_key`, `unpackerr_sonarr_api_key`
- **Selfhosted**: `changedetection_api_key`, `changedetection_notification_url`, `karakeep_nextauth_secret`, `karakeep_meili_master_key`, `karakeep_openrouter_api_key`, `karakeep_api_key`, `paperless_secret_key`, `paperless_admin_user`, `paperless_admin_password`, `paperless_api_token`, `paperless_ai_openai_api_key`, `paperless_ai_jwt_secret`, `gatus_telegram_token`, `gatus_telegram_chatid`, `security_notifier_telegram_token`, `security_notifier_telegram_chatid`

## Argo CD & Apps
- ApplicationSet uses go-template and orders Applications via `argocd.argoproj.io/sync-wave` (taken from `sync.wave`; lower = earlier). RollingSync and progressive syncs are **not** used; remove any legacy `rollout.*` fields when touching app configs.
- Current wave ladder (use these numbers when adding apps):
  - `-5` base system + CRDs: argocd, coredns, metrics-server, multus, local-path-provisioner, cert-manager (controller/CRDs), external-secrets, gateway-api, istio-base, metacontroller, reloader
  - `-4` metacontroller consumers / DNS publishers / sensors: homelab-controller, external-dns-{internal,external}, falco
  - `-3` service mesh + authn: istio (also owns its gateway Issuers/Certificate and ExternalSecret), dex, oauth2-proxy
  - `-2` edge: cloudflared
  - `-1` time-sync webhook: k8tz
- `0` default catch-all (all other apps)
- PKI manifests for Istio (gateway Issuers, wildcard cert, Cloudflare ExternalSecret) live in `apps/platform-system/istio/manifests`; `apps/platform-system/cert-manager` only installs the controller/CRDs.
- Destination namespace defaults to the group directory unless overridden in `config.yaml`.
- ApplicationSet hardcodes `ServerSideApply=true` for every app (per-app `sync.serverSideApply` is removed).
- ApplicationSet sync options now omit `PruneLast`/`RespectIgnoreDifferences`; no global `ignoreDifferences` block—trust SSA/diffs.
- Argo CD controller runs with server-side diff enabled (`controller.diff.server.side=true`).
- Argo CD configmap ignores status-only changes for all resources (`resource.ignoreResourceUpdatesEnabled=true` + `resource.customizations.ignoreResourceUpdates.all` jsonPointer `/status`).
- ValidatingWebhookConfiguration caBundle/failurePolicy drift is ignored globally via `resource.customizations.admissionregistration.k8s.io/ValidatingWebhookConfiguration` jqPathExpressions in Argo CD values.
- k8tz webhook TLS uses a namespace-scoped Issuer `k8tz-webhook-issuer` (see `apps/kube-system/k8tz/manifests/k8tz-webhook-issuer.issuer.yaml`); k8tz values enable cert-manager webhook issuer. A PreSync hook Job (`k8tz-wait-cert-manager`, delete policy `HookSucceeded`) waits for the `cert-manager-startupapicheck` Job to complete and the cert-manager, webhook, and cainjector Deployments to be Available in `platform-system` before k8tz sync proceeds. Supporting SA/ClusterRole/Binding are PreSync hooks with weight -1 so RBAC exists before the Job; delete policy `HookSucceeded` to retain evidence on failure.
- oauth2-proxy is pinned to chart 9.0.1 with OIDC groups support, cookie-based sessions, and gateway ext-auth applied only on HTTPS listeners (auth/id hosts and `/oauth2/*` bypassed). Shared wildcard `/oauth2/*` route removed; only auth.{external,internal} routes remain.
- Gateway ext-auth forwards identity headers (`x-auth-request-user`, `x-auth-request-email`, `x-auth-request-groups`) via Istio `headersToUpstreamOnAllow` with oauth2-proxy `set-xauthrequest` enabled, while keeping `Authorization`/access-token passthrough disabled and legacy `X-Forwarded-*`/Basic auth headers suppressed. Backends consume only the x-auth-request identity headers.
- Dex runs with static config in `values.yaml` (no metacontroller, no external connectors). Update the static password hash in `dex-credentials` ExternalSecret.
- Metacontroller renders Gatus configs; edit templates under `manifests/homelab-controller/`, never the generated `*-generated-config` ConfigMaps. Keep the implementations structurally aligned (only app-specific diffs).
- Homepage replaces Hajimari. External HTTPRoutes you want visible on the dashboard must carry `gethomepage.dev/enabled: "true"`, plus `gethomepage.dev/name`, `gethomepage.dev/group`, and `gethomepage.dev/icon` (use iconify values such as `mdi:...`). Default group is the namespace title-cased. Keep the existing `external-dns` labels.
- Enable Gatus by labeling Services `gatus.edgard.org/enabled: "true"`.
- Gateway API CRDs are installed via the `gateway-api` app from kubernetes-sigs/gateway-api releases. The CRDs file is downloaded from GitHub and stored in manifests; update by downloading the new version's `standard-install.yaml`.
- Istio ingress uses Gateway API with two Gateways: `gateway-external` (wildcard + root over HTTPS, external-dns target tunnel.edgard.org) and `gateway-internal` (wildcard + root, macvlan IP 192.168.1.241). We rely on the built-in `istio` GatewayClass (no custom GatewayClass objects). Gateway API resources now live in `platform-system/istio` alongside istiod; the Istio controller auto-provisions the data-plane Deployments/Services (Service type forced to ClusterIP via `gateway.istio.io/serviceType: ClusterIP`). OIDC is enforced via the ext-auth `oauth2-proxy` provider (Dex IdP, cookie domain `.edgard.org`). Sidecar injector is disabled (`sidecarInjectorWebhook.enabled=false`, `global.proxy.autoInject=disabled`) to keep the deployment gateway-only. Istio charts pull from `https://istio-release.storage.googleapis.com/charts` (base/istiod).
- Istio webhooks: controller mutates failurePolicy/caBundle; Argo ignores those fields on `istiod-default-validator` and `istio-validator-platform-system` to avoid drift.
- CoreDNS override lives at `apps/kube-system/coredns/values.yaml`; it forwards `edgard.org` to Unifi (192.168.1.1) but pins `id.edgard.org` to the internal Istio gateway IP (192.168.1.241) for in-cluster OIDC.

## Storage
- Reuse Kind’s built-in local-path-provisioner; we only manage config + StorageClasses under `apps/local-path-storage/local-path-provisioner/manifests`.
- ConfigMap `local-path-config` (namespace `local-path-storage`) sets node paths `/mnt/spool/appdata` and `/mnt/dpool`; pathPattern `{{ .PVC.Namespace }}/{{ .PVC.Name }}` for fast, `{{ .PVC.Name }}` for bulk.
- StorageClasses:
  - `local-fast` (default): RWO, `WaitForFirstConsumer`, base `/mnt/spool/appdata` with `namespace/claim` subpaths.
  - `local-bulk`: RWO, base `/mnt/dpool`, pathPattern claim name (so PVC `media` maps to `/mnt/dpool/media`).
- Media PVC is dynamic on `local-bulk` (`media` in namespace `media`, maps to `/mnt/dpool/media`).
- Bootstrap demotes Kind's built-in `standard` StorageClass (if present) so `local-fast` becomes the sole default.
- Restic repo and www now use dynamic PVCs on `local-bulk` (sizes set in their values files); move host data into the provisioned paths when migrating.
- Base paths `/mnt/spool/appdata` and `/mnt/dpool` must exist on the Kind host; worker already mounts `/mnt/spool` and `/mnt/dpool`.
- Char devices `/dev/net/tun` and `/dev/ttyUSB0` remain hostPath mounts where needed; restic keeps hostPath `/mnt/spool/appdata` for backup source coverage.
- Helper scripts in repo root:
  - `migrate-pvc-data.sh` (dry-run by default, use `DRY_RUN=0`) to rsync old hostPath data into new PVC paths.
  - `cleanup-old-hostpaths.sh` (dry-run by default) to remove legacy hostPath directories after migration.

## Commands
- Lint/format YAML: `task lint` (prettier ➜ yamlfmt ➜ yamllint).
- Secrets: All secrets are managed in Bitwarden Secrets Manager. Set `BWS_ACCESS_TOKEN` environment variable before running `task bootstrap:create`.
- Argo resync without CLI: `task argo:sync app=name` (omit `app` to refresh all).
- Argo UI port-forward: `task argo:pf` (forwards `svc/argocd-server` on 8080→80).
- Renovate: `.renovaterc.json5` tracks Helm charts in `apps/*/*/config.yaml`, Kind node images, WASM plugins in `apps/*/*/manifests/*.wasmplugin.yaml` (docker datasource), and Gateway API CRDs version (github-releases datasource).
- Istio charts are pinned to the `platform-system` namespace via `global.istioNamespace`/`configRootNamespace`; validation failure policy is set to `Ignore`. Argo no longer ignores Istio webhook CA bundle drift (expect SSA to update it).
- Terraform: `task tf:plan|tf:apply|tf:validate|tf:clean` (default dir `terraform`). Env required: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` (B2 backend), `CLOUDFLARE_API_TOKEN`, `TF_VAR_cloudflare_zone_id`. `.envrc` provides local values—do not commit rotations here.

## Coding Style & Patterns
- YAML: 2-space indent; logical ordering (metadata → spec/values); filenames track chart/app names; keep `manifests/` only when it contains real manifests (or when required by the ApplicationSet).
- Python (`bootstrap/`): type hints, f-strings, existing logging style; run `python3 -m compileall bootstrap` after edits.
- Conventional Commits (`feat:`, `fix:`, `refactor:`, `chore(deps):`, etc.). Keep PRs focused; note validation steps (lint, Kind/Argo checks) and any manual rollout actions.
- Follow existing organization/naming conventions for Argo CD applications and Kubernetes resources (detailed in "Resource Naming Conventions" and "App-Template House Style" sections).

## Resource Naming Conventions
All Kubernetes resources follow consistent naming patterns. Filename must always match `metadata.name`.

### Manifest Files
- Pattern: `{app}-{descriptor}.{kind}.yaml`
- The `{app}` prefix must match the app directory name
- The `{descriptor}` describes what the resource does/is
- The `{kind}` suffix is the lowercase Kubernetes kind
- Examples: `istio-credentials.externalsecret.yaml`, `gateway-external.gateway.yaml`

### Secrets (ExternalSecrets)
- Pattern: `{app}-credentials`
- All ExternalSecrets create secrets with `-credentials` suffix
- Exception: `argocd-secret` (ArgoCD's built-in secret, we merge into it with `creationPolicy: Merge`)
- Examples: `restic-credentials`, `oauth2-proxy-credentials`, `dex-credentials`

### TLS Certificate Secrets
- Pattern: `{app}-{descriptor}-tls`
- Example: `gateway-wildcard-tls` (created by istio Certificate resource)

### Generated ConfigMaps (homelab-controller)
- Pattern: `{app}-generated-config`
- These are auto-generated by homelab-controller from GatusConfig CRs
- Examples: `gatus-generated-config`
- Never edit these directly; modify the source CR's `spec.base` instead

### Issuers (istio)
- Pattern: `gateway-issuer-{environment}`
- Examples: `gateway-issuer-production`, `gateway-issuer-staging`

### Gateways (Istio)
- Pattern: `gateway-{scope}`
- Examples: `gateway-external`, `gateway-internal`
- Related resources (ReferenceGrant, ConfigMap) use same prefix: `gateway-external.referencegrant.yaml`

### HTTPRoutes
- Pattern: `{app}-{purpose}` or `gateway-{purpose}`
- Examples: `oauth2-proxy-auth-external`, `gateway-https-redirect`, `gateway-root-redirect`

### ServiceAccounts & fullnameOverride
- Must match the app directory name exactly
- Examples: `external-dns-external`, `external-secrets`, `metrics-server`

### ClusterSecretStore
- Single store: `external-secrets-store`
- All ExternalSecrets reference this via `secretStoreRef.name`

### Custom Resource Definitions
- Pattern: `{plural}.{group}` (FQDN style)
- Examples: `gatusconfigs.homelab.edgard.org`

### Summary Table
| Resource Type | Pattern | Example |
|---------------|---------|---------|
| ExternalSecret | `{app}-credentials` | `gateway-credentials` |
| TLS Secret | `{app}-{desc}-tls` | `gateway-wildcard-tls` |
| Generated ConfigMap | `{app}-generated-config` | `gatus-generated-config` |
| Gateway | `gateway-{scope}` | `gateway-external` |
| Issuer | `{app}-issuer-{env}` | `gateway-issuer-production` |
| HTTPRoute | `{app}-{purpose}` | `oauth2-proxy-auth-external` |
| CRD | `{plural}.{group}` | `gatusconfigs.homelab.edgard.org` |

## Testing & Safety
- Baseline: `task lint`.
- Targeted manifest tweaks (rare): use `kubectl diff -f <path>` for dry-run inspection only. Do not `kubectl apply`/`kubectl patch` Argo-managed resources—Argo sync will overwrite; make changes in Git and let Argo reconcile.
- When updating Argo Applications, confirm chart `targetRevision` matches the intended release to avoid drift.
- Never commit secrets or the `BWS_ACCESS_TOKEN` environment variable.

## App-Template House Style (bjw-s app-template v4.5.0)

This repo uses the bjw-s-labs Helm chart `app-template` for many apps.
Goal: keep `apps/*/*/values.yaml` for app-template apps visually aligned so new apps are mostly copy/paste.

### Scope

Applies to apps whose `apps/*/*/config.yaml` sets:

- `chart.repo: oci://ghcr.io/bjw-s-labs/helm/app-template`

### House style (values.yaml)

- Top-level key ordering (when present): `defaultPodOptions` -> `controllers` -> `serviceAccount`/`rbac` -> `service` -> `route` -> `persistence` -> `configMaps`/`secrets`.
  Note: key ordering is not semantically required by YAML/Helm; this is a readability convention.
- Prefer `controllers.main` for single-component apps; add more controllers only when needed.
- Primary container name is always `containers.app` (not `containers.main`).
- Deployments: prefer `replicas: 1` and `strategy: Recreate` when possible (single worker node cluster; avoids RWO PVC and port conflicts during rolling updates).
- Persistence: prefer naming the primary persistent volume `persistence.data` (not `<app>-data`) for consistency across apps.
- Use the simplified probe structure:

  ```yaml
  probes:
    startup:
      enabled: true
    liveness:
      enabled: true
    readiness:
      enabled: true
  ```

### Persistence naming

For consistency across apps, the primary persistent volume should be `persistence.data` whenever the app needs durable state (db/config/library/etc).

Guidelines:

- `persistence.data`: main PVC for the app's stateful data.
- `persistence.config`: configMap/Secret mounts (not the main PVC).

- Use additional PVCs only when they have a distinct purpose (example: `media`), and name them by purpose.
- Caution: renaming a `persistence.*` key typically changes the underlying volume/PVC name; do not rename existing PVC-backed volumes without a deliberate migration plan.

### Security contexts

We use two layers: pod defaults (`defaultPodOptions`) and per-container `securityContext`.

#### Pod defaults (`defaultPodOptions.securityContext`)

Baseline (applied everywhere):

```yaml
defaultPodOptions:
  securityContext:
    fsGroupChangePolicy: OnRootMismatch
```

Non-root profile (use when the workload can reliably run as a fixed UID/GID):

```yaml
defaultPodOptions:
  securityContext:
    fsGroup: <uid>
    fsGroupChangePolicy: OnRootMismatch
    runAsGroup: <uid>
    runAsNonRoot: true
    runAsUser: <uid>
```

Preferred default when possible: UID/GID `568` (consistent with many apps in this repo).

```yaml
defaultPodOptions:
  securityContext:
    fsGroup: 568
    fsGroupChangePolicy: OnRootMismatch
    runAsGroup: 568
    runAsNonRoot: true
    runAsUser: 568
```

#### Container baseline (`controllers.*.containers.*.securityContext`)

Baseline (applied everywhere):

```yaml
securityContext:
  allowPrivilegeEscalation: false
```

Strict profile (use when the container works with restricted capabilities):

```yaml
securityContext:
  allowPrivilegeEscalation: false
  capabilities:
    drop:
      - ALL
```

Common exceptions:

- Bind to ports <1024 as non-root: add `NET_BIND_SERVICE`.
- VPN/tunnels: may require caps like `NET_ADMIN` (example: gluetun).
- Hardware access: `privileged: true` and/or hostPath devices as needed.

If `readOnlyRootFilesystem: true` is enabled, ensure all writable paths are explicitly mounted. For `/tmp`, applications often rely on the default ephemeral storage provided by the container runtime rather than an explicit `emptyDir` mount in the `values.yaml` file. If an application needs a persistent or specific temporary storage, an explicit mount is required.

### Current status (app-template apps)

Definitions:

- Baseline compliant: matches our repo baseline (`defaultPodOptions.securityContext.fsGroupChangePolicy: OnRootMismatch`, primary container name `app`, and `securityContext.allowPrivilegeEscalation: false` on all containers).
- Fully compliant: baseline + strict-ready (non-root + `capabilities.drop: [ALL]`) where applicable.

| App | Fully compliant | Baseline compliant | Exceptions / notes |
|---|---|---|---|
| `apps/home-automation/home-assistant` | yes | yes | Runs as UID/GID 1000. |
| `apps/home-automation/mosquitto` | yes | yes | Runs as UID/GID 1883. |
| `apps/home-automation/zigbee2mqtt` | no | no | Container `main.app` is `privileged: true`. |
| `apps/kube-system/coredns` | n/a | n/a | No app-template controllers; values are used to manage configMaps. |
| `apps/local-path-storage/local-path-provisioner` | n/a | n/a | No app-template controllers; app-template used as a wrapper for manifests/values. |
| `apps/media/bazarr` | yes | yes | Runs as UID/GID 568. |
| `apps/media/flaresolverr` | yes | yes | Runs as UID/GID 1000. |
| `apps/media/jellyfin` | yes | yes | Runs as UID/GID 568. |
| `apps/media/prowlarr` | yes | yes | Runs as UID/GID 568. |
| `apps/media/qbittorrent` | no | yes | `gluetun` sidecar requires `NET_ADMIN` and likely runs as root. |
| `apps/media/radarr` | yes | yes | Runs as UID/GID 568. |
| `apps/media/recyclarr` | yes | yes | Runs as UID/GID 1000. |
| `apps/media/sonarr` | yes | yes | Runs as UID/GID 568. |
| `apps/media/unpackerr` | yes | yes | Runs as UID/GID 568. |
| `apps/platform-system/cloudflared` | yes | yes | Runs as UID/GID 65532. |
| `apps/platform-system/dex` | yes | yes | Runs as UID/GID 1001. |
| `apps/platform-system/gateway-api` | n/a | n/a | No app-template controllers; app-template used as a wrapper for manifests/values. |
| `apps/platform-system/homelab-controller` | yes | yes | Runs as UID/GID 1000. |
| `apps/platform-system/restic` | no | yes | Intentionally runs as root (UID/GID 0). |
| `apps/selfhosted/atuin` | yes | yes | Runs as UID/GID 1000. |
| `apps/selfhosted/changedetection` | yes | yes | `defaultPodOptions` are compliant; the `browser-sockpuppet-chrome` container might be less strict. |
| `apps/selfhosted/echo` | yes | yes | Runs as UID/GID 1000. |
| `apps/selfhosted/gatus` | yes | yes | Runs as UID/GID 1000. |
| `apps/selfhosted/homepage` | yes | yes | Runs as UID/GID 1000. |
| `apps/selfhosted/karakeep` | no | no | Security context configuration not found in `app-template` style in `values.yaml`. |
| `apps/selfhosted/nginx` | no | no | Security context configuration not found in `app-template` style in `values.yaml`. |
| `apps/selfhosted/paperless` | no | no | Security context configuration not found in `app-template` style in `values.yaml`.

### How to evaluate an app for security profile improvements

To assess an application's potential for non-root and strict security profiles:
- Review upstream documentation for recommended UIDs/GIDs, writable paths, and capabilities.
- Inspect Docker image metadata for default user and filesystem expectations.
- Test with non-root settings (e.g., UID/GID 568) and progressively enable stricter controls (`capabilities.drop: [ALL]`), ensuring all necessary writable paths are provided via mounts (e.g., `/tmp`).
