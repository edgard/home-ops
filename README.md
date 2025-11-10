# home-ops

Kind hosts the homelab cluster, Argo CD reconciles it, and each workload is a values-only Helm release with optional Kustomize resources (mainly SealedSecrets).

## Repository map

- `bootstrap/` – Kind config + `bootstrap.sh`, which installs Argo CD and applies `kubernetes/clusters/homelab/root-application.yaml`.
- `kubernetes/clusters/homelab/` – namespaces, Applications, and the kustomization synced by the root app.
- `kubernetes/apps/<namespace>/<app>/values.yaml` – Helm values per workload; `resources/` carries ConfigMaps, middlewares, and `*.sealedsecret.yaml`.
- `.git-secret.yaml` (untracked) – Argo repository credentials; bootstrap applies it to `argocd/home-ops-git` (example below).

## Prerequisites

- CLI deps: `docker`, `kind`, `kubectl`, `helm`, `yq`, `kubeseal`, `openssl`.
- Docker context `kind-<cluster>` pointing at the host that runs the Kind nodes (`homelab` by default).
- Sealed Secrets keypair stored as `.sealed-secrets.key` / `.sealed-secrets.crt`. Generate once:
  ```bash
  openssl req -x509 -nodes -newkey rsa:4096 \
    -keyout .sealed-secrets.key -out .sealed-secrets.crt \
    -days 3650 -subj "/CN=sealed-secrets/O=home-ops"
  ```
- `.git-secret.yaml` in the repo root (untracked) plus any host paths referenced by `bootstrap/cluster-config.yaml`.

## Networking & TLS

- `platform-system/ingress-nginx` provides the default ingress class and attaches to the `lan-macvlan` Multus network with static IP `192.168.1.241`.
- cert-manager + `clusterissuer.yaml` issue a wildcard `*.edgard.org` cert via Cloudflare DNS-01; Emberstack Reflector copies `wildcard-edgard-org-tls` into application namespaces. Add new namespaces to the certificate annotations before rolling out ingresses there and keep `tls.secretName: wildcard-edgard-org-tls` on every ingress.
- `platform-system/external-dns` (chart v1.19.0) publishes ingress hosts + DNSEndpoints to Cloudflare. Provide a Zone:DNS edit token via `external-dns.sealedsecret.yaml`, reseal it, and update `kubernetes/apps/platform-system/cloudflared/resources/cloudflared-dnsendpoint.yaml` with the actual `<tunnel-id>.cfargotunnel.com`.
- `platform-system/external-dns-unifi` reuses the chart with the UniFi webhook (`ghcr.io/kashalls/external-dns-unifi-webhook`) and only watches Services so LAN DNS mirrors Cloudflare. Annotate each ingress-backed Service with `external-dns.alpha.kubernetes.io/hostname` and `external-dns.alpha.kubernetes.io/target: 192.168.1.241`, set `UNIFI_HOST` in its `values.yaml`, and reseal `external-dns-unifi.sealedsecret.yaml` with the controller API key.

## Secrets & identity

- Commit only sealed manifests: create a plaintext Secret locally, run `kubeseal --cert .sealed-secrets.crt --format yaml`, and list the resulting `<name>.sealedsecret.yaml` inside `resources/kustomization.yaml`.
- Dex (`platform-system/dex`) provides authentication. Rotate static users or OAuth clients by editing the plaintext config, generating bcrypt hashes with `htpasswd -nbB -C 10`, resealing `dex-config.sealedsecret.yaml`, and syncing the Application. Replace the default admin password and oauth2-proxy secret right after bootstrap.

## Bootstrap

1. Review `bootstrap/cluster-config.yaml` plus any workload `values.yaml` overrides.
2. Ensure `.sealed-secrets.key`, `.sealed-secrets.crt`, `.git-secret.yaml`, and required host paths exist.
3. Run `make bootstrap`. The script creates (or reuses) the Kind cluster, seeds `kube-system/sealed-secrets-key`, installs Argo CD with `bootstrap/argocd-values.yaml`, and applies the root Application so every namespace + workload syncs.
4. Watch progress with `kubectl -n argocd get applications`, `make argo-apps`, or the Argo UI/CLI. Use `make argo-admin-secret` for the initial password if you need to log in.

## Day-2 operations

- Workload changes: edit the relevant `values.yaml` or `resources/`, commit, and push—Argo reconciles automatically. Use `make argo-sync APP=<name>` or `argocd app sync <name>` for a forced refresh.
- Namespaces with ingresses: create the namespace manifest, add it to `kubernetes/clusters/homelab/namespaces`, update `wildcard-certificate.yaml` reflection annotations, sync cert-manager + reflector, then deploy the workload.
- Secrets: re-run the `kubeseal` flow for any rotation, reseal with the current `.sealed-secrets.crt`, and commit only the sealed output.
- Troubleshooting: `make argo-apps` lists status, `make argo-port-forward` exposes the UI on `localhost:8080`, and `argocd app get <name>` shows health/sync info. Delete or recreate Kind clusters via `make kind-*` targets when you need a clean environment.

## Make targets

- `make bootstrap | bootstrap-delete | bootstrap-recreate` – run or reset `bootstrap/bootstrap.sh`.
- `make kind-create | kind-delete | kind-recreate | kind-status` – manage the Kind cluster directly.
- `make argo-apps`, `make argo-sync APP=<name>`, `make argo-port-forward` – inspect, sync, or port-forward Argo CD.
- `make argo-admin-secret` – print the decoded `argocd-initial-admin-secret`.
- `make sealed-secrets-fetch-cert` / `make sealed-secrets-seal SECRET_IN=... SEALED_OUT=...` – manage the Sealed Secrets certificate and reseal plaintext manifests.

## Example `.git-secret.yaml`

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: home-ops-git
  namespace: argocd
  labels:
    argocd.argoproj.io/secret-type: repository
stringData:
  url: https://github.com/edgard/home-ops.git
  username: argocd
  password: ghp_yourTokenHere
```

## Changes & testing

Renovate tracks charts, containers, Kind images, and CI. Review its PRs like any other change, run dry-runs or a `make bootstrap` smoke test for major upgrades, and merge once Argo reports healthy syncs. Update this document whenever bootstrap, ingress, or validation flows change.
