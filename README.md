# homelab

 Kind runs a control-plane + worker pair (Kind v1.34.0) and Flux keeps everything reconciled. The worker mounts `/mnt/spool`, `/mnt/dpool`, `/dev/net/tun`, and `/dev/ttyUSB0`, Multus provides LAN access through the `lan-macvlan` NAD, and Envoy Gateway exposes both internet and LAN HTTPRoutes so every workload can publish OAuth-protected and internal-only endpoints. Observability stacks (kube-prometheus-stack, Loki, Alloy, blackbox-exporter, etc.) remain removed until we reintroduce that namespace. `README.md` and `AGENTS.md` stay in lockstep whenever bootstrap flows, Flux conventions, or namespace wiring changes.

## Layout
- `cluster/config/` – Kind config plus the encrypted `cluster-secrets.sops.yaml` template bundle.
- `cluster/flux/ks.yaml` – defines the `cluster-infra` and `cluster-apps` Flux `Kustomization` CRs (both in `flux-system`) and injects the shared HelmRelease install/upgrade patch.
- `infra/<namespace>/<app>/` – infrastructure controllers grouped by namespace. `infra/flux-system` holds the Flux operator/instance while `infra/platform-system` owns Multus, ESO, cert-manager, Envoy Gateway, DNS, cloudflared, Dex, metrics-server, reloader, etc.; each namespace folder ships a `namespace.yaml` (so Flux manages labels/annotations) plus `app/` manifests with a co-located `ks.yaml`.
- `apps/<namespace>/<app>/` – namespace workloads with the same `app/` structure plus per-app `ks.yaml` files; `apps/<namespace>/kustomization.yaml` lists the namespace + workloads.
- `Makefile` – `make bootstrap`, Kind helpers, secrets tooling, and `make flux-reconcile`.

## Quickstart
1. Install `docker`, `kind`, `kubectl`, `helm`, `python3` (with `pyyaml`), `sops`, and `age`.
2. Run `make secrets-create-key` (creates `.sops.agekey`).
3. Copy `cluster/config/cluster-secrets.template.yaml` to `cluster/config/cluster-secrets.sops.yaml` and fill the placeholders (Flux sync creds, Dex config, Envoy OIDC secret, Cloudflare + UniFi API tokens, `cloudflared_tunnel_token`, Kopia password, qbittorrent WireGuard data, Unpackerr API keys, Telegram tokens, ARC GitHub App creds, etc.).
4. Manage the encrypted bundle with `make secrets-edit` / `make secrets-apply`. Never commit the decrypted `.cluster-secrets.yaml`—bootstrap decrypts it temporarily so ESO can mirror the values.
5. Run `make bootstrap`. The helper in `scripts/bootstrap.py` prepares/validates the Docker context, creates or updates Kind from `cluster/config/cluster-config.yaml`, attaches worker nodes to the `kind-<cluster>-net` macvlan (parent `br0` by default), ensures the `platform-system` namespace exists, applies `cluster-secrets.sops.yaml`, installs `flux-operator@0.33.0` + `flux-instance@0.33.0` into `flux-system`, creates the optional `flux-sync` Secret when the repo is private, renders the FluxInstance manifest from `infra/flux-system/flux-instance/app/helmrelease.yaml`, and stops once the FluxInstance reports Ready so Flux can reconcile `cluster/flux`.
6. Need a different LAN bridge or subnet? Export `MULTUS_PARENT_IFACE`, `MULTUS_PARENT_SUBNET`, `MULTUS_PARENT_GATEWAY`, or `MULTUS_PARENT_IP_RANGE` before step 5.

## Networking & ingress
- `infra/platform-system/multus/config/lan-macvlan.yaml` declares the static macvlan interface on `eth1` inside the nodes (bridge mode). Reserve MAC/IP pairs ahead of time—Envoy internal (192.168.1.241/24, `02:42:c0:a8:01:f1`), jellyfin (192.168.1.245/24, `02:42:c0:a8:01:f5`), and home-assistant (192.168.1.246/24, `02:42:c0:a8:01:f6`) already consume leases.
- Envoy Gateway v1.6.0 installs via `infra/platform-system/envoy-gateway` plus `infra/platform-system/envoy-gateway/config`. Two Gateways (`external`, `internal`), EnvoyProxy definitions, HTTP→HTTPS redirects, ReferenceGrants, shared policies, Services, and the Envoy OIDC client ClusterExternalSecret all live there.
- Every workload ships external/internal HTTPRoutes. External routes target the `external` Gateway, add `external-dns.edgard.org/scope: external`, and carry a `gateway.envoyproxy.io/v1alpha1` `SecurityPolicy` when OAuth-protected (Dex at `https://id.edgard.org` using the shared `envoy-oidc-client` secret). Internal routes target the `internal` Gateway, carry the `internal` label, and skip auth.
- `infra/platform-system/cert-manager` (chart v1.19.1) issues `wildcard-edgard-org` via the `letsencrypt-cloudflare` ClusterIssuer. `infra/platform-system/external-dns-external` pushes proxied records into Cloudflare, while `infra/platform-system/external-dns-internal` (UniFi webhook v0.7.0) publishes split-horizon DNS. `infra/platform-system/cloudflared` runs `cloudflare/cloudflared:2025.11.1`, terminates the tunnel for `*.edgard.org`/`edgard.org`, and ships a `DNSEndpoint` so ExternalDNS knows about `tunnel.edgard.org`.

## Flux topology & dependencies
- `cluster-infra` renders `infra/kustomization.yaml`; `cluster-apps` depends on it and renders `apps/kustomization.yaml`.
- `flux-system` ordering: `flux-instance` depends on `flux-operator`; `cluster-apps` depends on `cluster-infra`.

**Infrastructure Kustomizations**

| Namespace | Kustomization | Depends on |
| --- | --- | --- |
| `flux-system` | `flux-instance` | `flux-operator` |
| `flux-system` | `cluster-apps` | `cluster-infra` |
| `platform-system` | `platform-system-multus` | `flux-instance` |
| `platform-system` | `platform-system-multus-config` | `platform-system-multus` |
| `platform-system` | `platform-system-external-secrets` | `platform-system-multus-config` |
| `platform-system` | `platform-system-external-secrets-config` | `platform-system-external-secrets` |
| `platform-system` | `platform-system-metrics-server` | `platform-system-multus-config` |
| `platform-system` | `platform-system-reloader` | `platform-system-multus-config` |
| `platform-system` | `platform-system-cert-manager` | `platform-system-external-secrets-config` |
| `platform-system` | `platform-system-cert-manager-config` | `platform-system-cert-manager` |
| `platform-system` | `platform-system-envoy-gateway` | `platform-system-cert-manager-config` |
| `platform-system` | `platform-system-envoy-gateway-config` | `platform-system-envoy-gateway`, `platform-system-external-secrets-config` |
| `platform-system` | `platform-system-external-dns-external` | `platform-system-envoy-gateway-config` |
| `platform-system` | `platform-system-external-dns-internal` | `platform-system-envoy-gateway-config` |
| `platform-system` | `platform-system-cloudflared` | `platform-system-external-dns-external` |
| `platform-system` | `platform-system-dex` | `platform-system-envoy-gateway-config` |

**Application Kustomizations**

| Namespace | Kustomization | Depends on |
| --- | --- | --- |
| `home-automation` | `home-automation-zigbee2mqtt` | `home-automation-mosquitto` |
| `home-automation` | `home-automation-home-assistant` | `home-automation-zigbee2mqtt` |
| `media` | `media-radarr` | `media-qbittorrent` |
| `media` | `media-sonarr` | `media-qbittorrent` |
| `media` | `media-prowlarr` | `media-flaresolverr` |
| `arc` | `arc-runners` | `arc-controller` |

Other workloads reconcile independently.

## Commands & testing
- `make bootstrap` / `bootstrap-delete` / `bootstrap-recreate` – manage the full Kind + Flux environment. Use `make kind-*` for raw Kind operations and `make flux-reconcile` when you need Flux to refresh the Git artifact.
- `make yaml-check` – run `prettier --write "**/*.yml" "**/*.yaml" "!**/*.sops.yaml"`, then `yamlfmt`, and finally `yamllint .` so the entire tree is formatted and validated before committing.
- `make secrets-create-key`, `make secrets-edit`, `make secrets-apply` – manage the encrypted bundle.
- Debugging flows go through Flux: `flux get kustomizations cluster-infra cluster-apps -n flux-system`, `flux get kustomizations -n platform-system`, and `kubectl -n <namespace> describe kustomization/<name>` cover most needs.
- Treat `make bootstrap` as the integration test. After structural changes or chart bumps, rerun it (or at least `make flux-reconcile`) and wait for Flux to report `Ready` before merging. There is no ArgoCD—Flux is the single source of truth.

## Security & automation
- Keep `cluster-secrets.sops.yaml` encrypted, `.cluster-secrets.yaml` gitignored, and `.sops.agekey` private. Update `.sops.yaml` + re-encrypt if you relocate keys.
- Populate `flux_sync_username` / `flux_sync_password` when the repo is private so bootstrap can create the `flux-sync` Secret consumed by the FluxInstance Helm values.
- Regenerate Dex bcrypt hashes with `htpasswd -nbB user pass`, update `dex_config_yaml`, and rerun `make secrets-apply` + `make flux-reconcile` after rotations.
- Renovate tracks container images, Helm charts, the Kind node image, and GitHub Actions workflows. Validate its PRs with `make bootstrap` / `make flux-reconcile` and only merge once Flux reports healthy `Ready` status for the touched `Kustomization` objects.
