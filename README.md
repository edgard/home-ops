# homelab

Kind v1.34.0 runs a control-plane + worker pair, Flux keeps it reconciled, Multus exposes LAN IPs via the `lan-macvlan` NAD, and Envoy Gateway publishes OAuth-protected (Dex) and LAN-only HTTPRoutes. The worker node mounts `/mnt/spool`, `/mnt/dpool`, `/dev/net/tun`, and `/dev/ttyUSB0` so host storage, WireGuard, and radios stay available.

## Layout
- `cluster/config/` – Kind config plus the encrypted `cluster-secrets.sops.yaml` bundle.
- `cluster/flux/ks.yaml` – bootstraps the `cluster-infra` and `cluster-apps` Flux `Kustomization` roots and injects the shared HelmRelease patch.
- `infra/<namespace>/<app>/` – Flux operator + instance in `infra/flux-system`; Multus, ESO, cert-manager, Envoy Gateway, DNS, cloudflared, Dex, metrics-server, and reloader live under `infra/platform-system`, each with `namespace.yaml`, `app/`, and `ks.yaml`.
- `apps/<namespace>/<app>/` – workload manifests mirror the same structure; every namespace folder has `namespace.yaml`, per-app `app/` directories, and a namespace `kustomization.yaml`.
- `Makefile` – entry points for bootstrap, Kind helpers, secrets flow, linting, and Flux reconcile.

## Bootstrap
1. Install `docker`, `kind`, `kubectl`, `helm`, `python3` + `pyyaml`, `sops`, and `age`.
2. Generate `.sops.agekey` (`make secrets-create-key`), copy `cluster-secrets.template.yaml` to `cluster-secrets.sops.yaml`, and fill the required values (Flux sync creds, Dex admin bcrypt hash, Envoy OIDC secret, Cloudflare/UniFi tokens, `cloudflared_tunnel_token`, Kopia password, qbittorrent WireGuard data, Unpackerr keys, Telegram tokens, ARC GitHub App creds, etc.).
3. Edit/apply the encrypted bundle with `make secrets-edit` / `make secrets-apply`.
4. Run `make bootstrap`. The helper ensures prerequisites, creates or upgrades Kind from `cluster/config/cluster-config.yaml`, attaches the worker to `kind-<cluster>-net`, sets kubecontext, decrypts/applies `cluster-secrets.sops.yaml`, installs `flux-operator@0.33.0`, renders the FluxInstance HelmRelease, waits for the FluxInstance to become Ready, and hands control to Flux so it reconciles `cluster/flux`.
5. Override LAN plumbing by exporting `MULTUS_PARENT_IFACE`, `MULTUS_PARENT_SUBNET`, `MULTUS_PARENT_GATEWAY`, and/or `MULTUS_PARENT_IP_RANGE` before running bootstrap.

## Flux Topology
- Root ordering: `cluster-infra` applies `infra/kustomization.yaml`; `cluster-apps` depends on it and applies `apps/kustomization.yaml`.
- `flux-operator` installs before `flux-instance`; all platform controllers (Multus → Multus config → External Secrets → External Secrets config → cert-manager → cert-manager config → Envoy Gateway → Envoy Gateway config → External DNS → cloudflared → Dex) hang off that chain.
- Namespace `ks.yaml` files follow `<namespace>-<app>` naming so `flux get kustomizations` output stays predictable, and critical workloads carry explicit dependencies (e.g., Zigbee2MQTT waits for Mosquitto, Home Assistant waits for Zigbee2MQTT, Radarr/Sonarr wait for qbittorrent, Prowlarr waits for flaresolverr, ARC runners wait for the controller).

## Namespaces
- `kube-system` – managed by Kind; bootstrap leaves it untouched.
- `flux-system` – Flux operator + FluxInstance plus root `cluster-infra` / `cluster-apps`.
- `platform-system` – Multus/macvlan, External Secrets + ClusterSecretStore, metrics-server, Reloader, cert-manager (v1.19.1 + `letsencrypt-cloudflare` issuer), Envoy Gateway v1.6.0 (external/internal Gateways + EnvoyProxy + OIDC secret fan-out), External DNS (Cloudflare + UniFi webhook), cloudflared tunnel (2025.11.1) with `tunnel.edgard.org` `DNSEndpoint`, and Dex (config is versioned in `infra/platform-system/dex/app/helmrelease.yaml`, secrets come from `envoy-oidc-client` + `dex-static-password`).
- `ops` – gatus (status.edgard.org) and kopia (kopia.edgard.org) with Dex-protected HTTPRoutes.
- `home-automation` – Mosquitto, Zigbee2MQTT (privileged, `/dev/ttyUSB0`), and Home Assistant on Multus (`192.168.1.246/24`) with internal/external HTTPRoutes.
- `media` – LinuxServer apps (bazarr, radarr, sonarr, prowlarr), qbittorrent+gluetun, jellyfin on Multus (`192.168.1.245/24`), recyclarr, unpackerr.
- `edge-services` – nginx serving edgard.org/www, echo, atuin, changedetection (CronJob seeds notifications) with Dex policies where applicable.
- `arc` – GitHub Actions runner controller + scale set (Docker DinD sidecar, ARC secrets).

## Validation & Operations
- `make lint` (Prettier + `yamlfmt` + `yamllint`, all excluding `*.sops.yaml`) keeps YAML consistent.
- `make bootstrap` is the integration test—use it (or `make flux-reconcile`) after structural changes, chart bumps, or Renovate updates and wait for `flux get kustomizations cluster-infra cluster-apps -n flux-system` to show Ready.
- Day-2 checks: `flux get kustomizations -A`, `flux get sources git -n flux-system`, and `kubectl -n <namespace> describe kustomization/<name>`.
- Secrets stay encrypted: keep `.sops.agekey` private, rerun `make secrets-apply` after changes, and populate `flux_sync_username/password` for private repos so bootstrap can provision the pull secret.
- Renovate watches container images, charts, the Kind node image, and GitHub Actions workflows; validate its PRs with the same lint + bootstrap flow before merging.
