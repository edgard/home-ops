# home-ops

Kind v1.34.0 runs a control-plane + worker pair. The worker mounts `/mnt/spool`, `/mnt/dpool`, `/dev/net/tun`, and `/dev/ttyUSB0` so storage, WireGuard, and radios stay available. Multus (`lan-macvlan`) hands LAN IPs (Envoy internal 192.168.1.241, Jellyfin 192.168.1.245, Home Assistant 192.168.1.246); Envoy Gateway serves Dex-protected external routes and LAN-only internal routes. Flux keeps everything reconciled.

## Layout
- `cluster/config/` – Kind config plus the encrypted `cluster-secrets.sops.yaml` bundle.
- `cluster/flux/ks.yaml` – roots the `cluster-infra` / `cluster-apps` Flux `Kustomization` pair and injects the shared HelmRelease patch.
- `infra/<namespace>/<app>/` – infrastructure controllers (Flux operator/instance, Multus, ESO, cert-manager, Envoy Gateway, External DNS controllers, cloudflared, Dex, metrics-server, Metacontroller, Reloader) with `namespace.yaml`, `app/`, and `ks.yaml`.
- `apps/<namespace>/<app>/` – workloads follow the same pattern; each namespace has `namespace.yaml`, per-app `app/` directories, and a namespace `kustomization.yaml`.
- `Makefile` – entry points for bootstrap, Kind helpers, secrets flow, linting, and Flux reconcile. Helper targets are single-cluster scoped; there is no `CLUSTER` override.

## Bootstrap
1. Install `docker`, `kind`, `kubectl`, `helm`, `python3` + `pyyaml`, `sops`, and `age`.
2. Create `.sops.agekey` (`make secrets-create-key`), copy `cluster-secrets.template.yaml` to `cluster-secrets.sops.yaml`, and fill the required keys from the template (Flux sync credentials, ARC GitHub App, qbittorrent WireGuard data, Unpackerr keys, DNS/TLS tokens, cloudflared tunnel token, Envoy OIDC secret, Dex admin bcrypt hash, Kopia password, Gatus/changedetection tokens, manyfold secret, etc.).
3. Edit/apply the encrypted bundle with `make secrets-edit` / `make secrets-apply`.
4. Run `make bootstrap`. It checks prerequisites, ensures the `kind-<cluster>` Docker context exists, creates or upgrades Kind from `cluster/config/cluster-config.yaml`, patches Kindnet to drop resource requests, attaches the worker to `kind-<cluster>-net`, sets the kubecontext, decrypts/applies `cluster-secrets.sops.yaml`, installs `flux-operator@0.33.0`, creates the optional `flux-sync` Secret when Git creds are present, renders the FluxInstance from `infra/flux-system/flux-instance/app/helmrelease.yaml`, waits for the instance to become Ready, and stops so Flux reconciles `cluster/flux`.
5. Override LAN plumbing before bootstrap by exporting `MULTUS_PARENT_IFACE`, `MULTUS_PARENT_SUBNET`, `MULTUS_PARENT_GATEWAY`, or `MULTUS_PARENT_IP_RANGE`.

## Flux Topology
- Roots: `cluster-infra` applies `infra/kustomization.yaml`; `cluster-apps` depends on it and applies `apps/kustomization.yaml`.
- Platform chain in `platform-system`: Multus → Multus config → External Secrets → External Secrets config → cert-manager → cert-manager config → Envoy Gateway → Envoy Gateway config → External DNS (Cloudflare + UniFi webhook) → cloudflared → Dex; metrics-server, Metacontroller, and Reloader also hang off Multus config.
- Namespace `ks.yaml` files use `<namespace>-<app>` names so `flux get kustomizations` is readable. App dependencies stay explicit (Zigbee2MQTT → Mosquitto, Home Assistant → Zigbee2MQTT, Radarr/Sonarr → qbittorrent, Prowlarr → flaresolverr, ARC runners → controller).

## Namespaces
- `flux-system` – flux-operator, FluxInstance, GitRepository (`flux-system` source), `cluster-infra` / `cluster-apps`.
- `platform-system` – Multus (lan-macvlan NAD), External Secrets + ClusterSecretStore, metrics-server (drops requests, `--kubelet-insecure-tls`), Metacontroller, Reloader, cert-manager v1.19.1 + `letsencrypt-cloudflare` issuer and `wildcard-edgard-org` certificate, Envoy Gateway v1.6.0 (external/internal Gateways and EnvoyProxy), External DNS (Cloudflare + UniFi webhook), cloudflared 2025.11.1 with `tunnel.edgard.org` `DNSEndpoint`, Dex (`envoy-oidc-client` Secret fans to labeled namespaces).
- `ops` – gatus (status.edgard.org) and kopia (kopia.edgard.org), both Dex-protected.
- `home-automation` – Mosquitto, Zigbee2MQTT (privileged, `/dev/ttyUSB0`), Home Assistant on Multus `192.168.1.246/24`; HTTPRoutes skip Dex to use native auth.
- `media` – LinuxServer apps (bazarr/radarr/sonarr/prowlarr), flaresolverr, qbittorrent+gluetun (`/dev/net/tun`), jellyfin on Multus `192.168.1.245/24`, recyclarr, unpackerr.
- `edge-services` – nginx (`edgard.org`/`www`), hajimari dashboard at `apps.edgard.org` (Dex on external route) now rendered by a Metacontroller-managed `HajimariDashboard` CR + webhook instead of an init container, echo, atuin (auth handled by CLI), changedetection with Chrome sidecar and postStart-seeded notifications (no CronJob), manyfold; Dex policies on external routes where applicable.
- `arc` – GitHub Actions runner controller and the `arc-homelab` scale set (DinD sidecar, ARC secrets).

## Validation & Operations
- `make lint` (Prettier + `yamlfmt` + `yamllint`, skips `*.sops.yaml`) replaces `make yaml-check`; run before pushing.
- Treat `make bootstrap` as the integration test; after structural edits, chart bumps, or Renovate changes, rerun it or `make flux-reconcile` and wait for `flux get kustomizations cluster-infra cluster-apps -n flux-system` to show Ready.
- Day-2 checks: `flux get kustomizations -A`, `flux get sources git -n flux-system`, `kubectl -n <namespace> describe kustomization/<name>`.
- Secrets stay encrypted; keep `.sops.agekey` private and rerun `make secrets-apply` after changes. Populate `flux_sync_username/password` for private repos so bootstrap can create the pull secret.
- Renovate tracks container images, Helm charts, Kind node image, and GitHub Actions workflows; validate its PRs with lint + bootstrap before merging.
