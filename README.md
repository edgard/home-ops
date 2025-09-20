# home-ops

Kind hosts the homelab cluster, Argo CD keeps it reconciled, and each workload is a “values-only” Helm release with optional Kustomize resources (mainly SealedSecrets).

## Layout

- `bootstrap/` – Kind cluster config + `bootstrap.sh`, which installs Argo CD and applies `kubernetes/clusters/homelab/root-application.yaml`.
- `kubernetes/clusters/homelab/` – namespaces, application manifests, and the kustomization synced by the root app.
- `kubernetes/apps/<namespace>/<app>/values.yaml` – Helm values per workload; `resources/` holds extra manifests (ConfigMaps, middlewares, `*.sealedsecret.yaml`).
- `.git-secret.yaml` (untracked) – repository credentials Argo needs; bootstrap applies it to `argocd/home-ops-git` (see the example near the bottom of this document).

## Requirements

- CLI deps: `docker`, `kind`, `kubectl`, `helm`, `yq`, `kubeseal`, `openssl`.
- Docker context `kind-<cluster>` pointing at the host that runs the Kind nodes (default cluster name: `homelab`).
- Sealed Secrets keypair stored as `.sealed-secrets.key` / `.sealed-secrets.crt`. Generate once:
  ```
  openssl req -x509 -nodes -newkey rsa:4096 \
    -keyout .sealed-secrets.key -out .sealed-secrets.crt \
    -days 3650 -subj "/CN=sealed-secrets/O=home-ops"
  ```
- A `.git-secret.yaml` file (example below) and host paths that match `bootstrap/cluster-config.yaml`.

## Networking & TLS

- `platform-system-ingress-nginx` provides the default `nginx` ingress class. Each controller pod connects to the `lan-macvlan` Multus network with the static IP `192.168.1.241`.
- cert-manager (chart values in `kubernetes/apps/platform-system/cert-manager/values.yaml`) plus `clusterissuer.yaml` uses Cloudflare DNS-01 via the sealed `cloudflare-api-cert-manager` secret.
- All `*.edgard.org` hosts terminate TLS with one wildcard certificate (`kubernetes/apps/platform-system/cert-manager/resources/wildcard-certificate.yaml`). Emberstack Reflector (`platform-system-reflector` Application) mirrors `wildcard-edgard-org-tls` into `arc`, `home-automation`, `media`, `platform-system`, and `web`. Ingresses must only set `tls.secretName: wildcard-edgard-org-tls`; leave out `cert-manager.io/*issuer` annotations. Add new namespaces to the certificate’s reflection annotations before rolling out ingresses there.
- `platform-system-external-dns` (the upstream external-dns Helm chart v1.19.0 from `https://kubernetes-sigs.github.io/external-dns`) publishes ingress hosts and DNSEndpoint objects to Cloudflare. Provide an API token (Zone:DNS edit + Zone:Zone read on `edgard.org`) via `kubernetes/apps/platform-system/external-dns/resources/external-dns.sealedsecret.yaml`, reseal it, and sync the Argo Application. Every ingress includes `external-dns.alpha.kubernetes.io/target: tunnel.edgard.org`, so external-dns creates proxied CNAMEs aimed at the tunnel alias defined in `kubernetes/apps/platform-system/cloudflared/resources/cloudflared-dnsendpoint.yaml`. After creating the tunnel in Cloudflare, update that file’s `targets` entry to the real `<tunnel-id>.cfargotunnel.com` hostname so DNS stays in sync.

## Secrets & Identity

- Commit secrets as `SealedSecret` manifests inside each app’s `resources/` folder. To rotate:
  1. create a plaintext Secret locally (never commit it);
  2. `kubeseal --cert .sealed-secrets.crt --format yaml < secret.yaml > app/resources/<name>.sealedsecret.yaml`;
  3. list it in `resources/kustomization.yaml`.
- Dex (`platform-system-dex`) handles auth. Its config lives in `kubernetes/apps/platform-system/dex/resources/dex-config.sealedsecret.yaml`. Update passwords or OAuth clients by editing the plaintext source, running `htpasswd -nbB -C 10 user pass` for bcrypt hashes, resealing, and syncing the Argo app. Change the default admin account and oauth2-proxy secret immediately after bootstrap.

## Bootstrap

1. Review `bootstrap/cluster-config.yaml` and any app values you plan to customize.
2. Ensure `.sealed-secrets.key`, `.sealed-secrets.crt`, and `.git-secret.yaml` exist.
3. Run `make bootstrap`. The script:
   - creates or reuses the Kind cluster;
   - seeds `kube-system/sealed-secrets-key`;
   - installs Argo CD with `bootstrap/argocd-values.yaml`;
   - applies `root-application.yaml`, which syncs every namespace + Application (including cert-manager, ingress-nginx, reflector, etc.).
4. Track progress via `kubectl -n argocd get applications`, `make argo-apps`, or the Argo UI/CLI.

## Operations

- Tweak workloads by editing the relevant `values.yaml` (and optional `resources/`). Commit + push; Argo picks up the change.
- Need non-Helm YAML? Drop it into `resources/` with a `kustomization.yaml`.
- To force reconciliation: `make argo-sync APP=<name>` or `argocd app sync <name>`. Use `argocd app get <name>` for status.
- When adding a namespace with ingresses, update `wildcard-certificate.yaml` reflection annotations, sync `platform-system-cert-manager` + `platform-system-reflector`, then roll out the workload.

## Make targets

- `make bootstrap|bootstrap-delete|bootstrap-recreate` – drive `bootstrap/bootstrap.sh`.
- `make kind-create|kind-delete|kind-recreate|kind-status` – raw Kind lifecycle.
- `make argo-apps`, `make argo-sync APP=<name>`, `make argo-port-forward` – inspect/sync/port-forward Argo CD (`localhost:8080`).
- `make argo-admin-secret` – print the initial admin password without writing it to disk.
- `make sealed-secrets-fetch-cert` / `make sealed-secrets-seal SECRET_IN=...` – manage the Sealed Secrets public cert and reseal plaintext manifests.

## Example Argo repository secret (`.git-secret.yaml`)

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

## Updates

Renovate tracks charts, containers, Kind images, and CI. For each PR, review the changed `values.yaml` files, run any needed dry-runs, and merge after Argo reports healthy syncs (test majors on a throwaway Kind bootstrap if unsure). Update this README + `AGENTS.md` whenever bootstrap, ingress, or validation flows change.
