# home-ops

Kind hosts the homelab cluster, Argo CD reconciles it, and each workload is a values-only Helm release with optional Kustomize resources (ExternalSecrets, ConfigMaps, middlewares).

## Repository map

- `bootstrap/` – Kind config + `bootstrap.sh`, which installs Argo CD and applies `kubernetes/clusters/homelab/root-application.yaml`.
- `kubernetes/clusters/homelab/` – namespaces, Applications, and the kustomization synced by the root app.
- `kubernetes/apps/<namespace>/<app>/values.yaml` – Helm values per workload; `resources/` carries ConfigMaps, middlewares, and `ExternalSecret` manifests.
- `.central-secrets.yaml` (gitignored) – the aggregated secret bundle + Argo repo credentials. Keep it up to date locally (it creates the `kube-system/home-ops-central-secrets` Secret) and never commit it; bootstrap applies it before Argo starts reconciling.

## Prerequisites

- CLI deps: `docker`, `kind`, `kubectl`, `helm`, `yq`.
- Docker context `kind-<cluster>` pointing at the host that runs the Kind nodes (`homelab` by default).
- `.central-secrets.yaml` (untracked) containing the aggregated secret bundle and the repository credentials. Keep the file out of version control—bootstrap applies it automatically to `kube-system`.
- Any host paths referenced by `bootstrap/cluster-config.yaml`.

## Networking & TLS

- `platform-system/ingress-nginx` provides the default ingress class and attaches to the `lan-macvlan` Multus network with static IP `192.168.1.241`.
- cert-manager + `clusterissuer.yaml` issue a wildcard `*.edgard.org` cert via Cloudflare DNS-01; External Secrets Operator fans `wildcard-edgard-org-tls` into application namespaces (see `kubernetes/apps/platform-system/cert-manager/resources/wildcard-certificate-externalsecrets.yaml`). Keep `tls.secretName: wildcard-edgard-org-tls` on every ingress and add new namespaces to that file before deploying workloads there.
- `platform-system/external-dns` (chart v1.19.0) publishes ingress hosts + DNSEndpoints to Cloudflare. Define the Zone:DNS edit token inside `.central-secrets.yaml` and update `kubernetes/apps/platform-system/cloudflared/resources/cloudflared-dnsendpoint.yaml` with the actual `<tunnel-id>.cfargotunnel.com`.
- `platform-system/external-dns-unifi` reuses the chart with the UniFi webhook (`ghcr.io/kashalls/external-dns-unifi-webhook`) and only watches Services so LAN DNS mirrors Cloudflare. Annotate each ingress-backed Service with `external-dns.alpha.kubernetes.io/hostname` and `external-dns.alpha.kubernetes.io/target: 192.168.1.241`, set `UNIFI_HOST` in its `values.yaml`, and define the UniFi API key inside `.central-secrets.yaml`.

## Secrets & identity

- External Secrets Operator reads everything from `home-ops-central-secrets` (defined locally inside `.central-secrets.yaml` and created in the `kube-system` namespace). Keep that manifest out of Git and update it whenever credentials change.
- Include the Argo repository credentials in that same file: set `argocd_repo_url`, `argocd_repo_username`, and `argocd_repo_password` (if you still have `.git-secret.yaml`, copy its stringData values over, then delete the file).
- Dex (`platform-system/dex`) provides authentication. Rotate static users or OAuth clients by editing the `dex_config_yaml` entry in `.central-secrets.yaml` (bcrypt hashes still come from `htpasswd -nbB -C 10`), reapply the local secret (`kubectl apply -f .central-secrets.yaml`), and let the Dex ExternalSecret refresh. Replace the default admin password and oauth2-proxy secret right after bootstrap.

## Argo sync waves

Argo sync waves keep platform dependencies ordered; update this table whenever you add or reshuffle Applications so the README and AGENTS stay aligned.

| Purpose | Wave | Resources |
| --- | --- | --- |
| Kube-system bootstrap | `-10` | `kube-system-external-secrets`, `kube-system-metrics-server`, `kube-system-multus` |
| Startup gates | `-9` | `argocd-wait-for-multus`, `argocd-wait-for-external-secrets` |
| Ingress, TLS, and config reload | `-5` | `platform-system-ingress-nginx`, `platform-system-cert-manager`, `platform-system-reloader` |
| Identity + front-door networking | `-4` | `platform-system-dex`, `platform-system-cloudflared`, `platform-system-external-dns`, `platform-system-external-dns-unifi` |
| oauth2-proxy sidecar auth | `-3` | `platform-system-oauth2-proxy` |
| Default workloads | `0` | Any Application without an explicit wave annotation |
| ARC runner scale set | `1` | `arc-arc-home-ops` |

## Bootstrap

1. Review `bootstrap/cluster-config.yaml` plus any workload `values.yaml` overrides.
2. Ensure `.central-secrets.yaml` and required host paths exist.
3. Run `make bootstrap`. The script creates (or reuses) the Kind cluster, applies `.central-secrets.yaml`, installs Argo CD with `bootstrap/argocd-values.yaml`, and applies the root Application so every namespace + workload syncs.
4. Watch progress with `kubectl -n argocd get applications`, `make argo-apps`, or the Argo UI/CLI. Use `make argo-admin-secret` for the initial password if you need to log in.

## Day-2 operations

- Workload changes: edit the relevant `values.yaml` or `resources/`, commit, and push—Argo reconciles automatically. Use `make argo-sync APP=<name>` or `argocd app sync <name>` for a forced refresh.
- Namespaces with ingresses: create the namespace manifest, add it to `kubernetes/clusters/homelab/namespaces`, and list it inside the wildcard TLS ExternalSecret so ESO mirrors `wildcard-edgard-org-tls` there before the workload ships.
- Secrets: edit `.central-secrets.yaml`, apply it (`kubectl apply -f .central-secrets.yaml`), and wait for the relevant ExternalSecrets to report `Synced/Healthy`.
- Troubleshooting: `make argo-apps` lists status, `make argo-port-forward` exposes the UI on `localhost:8080`, and `argocd app get <name>` shows health/sync info. Delete or recreate Kind clusters via `make kind-*` targets when you need a clean environment.

## Make targets

- `make bootstrap | bootstrap-delete | bootstrap-recreate` – run or reset `bootstrap/bootstrap.sh`.
- `make kind-create | kind-delete | kind-recreate | kind-status` – manage the Kind cluster directly.
- `make argo-apps`, `make argo-sync APP=<name>`, `make argo-port-forward` – inspect, sync, or port-forward Argo CD.
- `make argo-admin-secret` – print the decoded `argocd-initial-admin-secret`.

## Changes & testing

Renovate tracks charts, containers, Kind images, and CI. Review its PRs like any other change, run dry-runs or a `make bootstrap` smoke test for major upgrades, and merge once Argo reports healthy syncs. Update this document whenever bootstrap, ingress, or validation flows change.
