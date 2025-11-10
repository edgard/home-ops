# home-ops

Kind hosts the homelab cluster, Argo CD reconciles it, and each workload is a values-only Helm release with optional Kustomize resources (ExternalSecrets, ConfigMaps, middlewares).

## Essentials

- Repo layout: `bootstrap/` holds the Kind + Argo installer, `kubernetes/clusters/homelab/` is the Argo root, and every workload lives under `kubernetes/apps/<namespace>/<app>`.
- Tooling: install `docker`, `kind`, `kubectl`, `helm`, `yq`, `sops`, and `age`, and point your Docker context at `kind-homelab` (or whatever `bootstrap/cluster-config.yaml` names).
- Secrets: run `make secrets-create-key` once to create `.sops.agekey`, then manage everything via the encrypted `bootstrap/central-secrets.sops.yaml` (`make secrets-edit` / `make secrets-apply`). The plaintext `.central-secrets.yaml` stays ignored so decrypted copies never get committed.

## Bootstrap workflow

1. Review `bootstrap/cluster-config.yaml` and any workload overrides.
2. Ensure `bootstrap/central-secrets.sops.yaml` exists (copy `bootstrap/central-secrets.template.yaml` if you need a starting point) and that `.sops.agekey` is present.
3. Run `make bootstrap`. The script creates the Kind cluster, decrypts and applies the central secrets, installs Argo CD using `bootstrap/argocd-values.yaml`, and applies `kubernetes/clusters/homelab/root-application.yaml`.
4. Watch sync status with `kubectl -n argocd get applications`, `make argo-apps`, or `make argo-port-forward`.

## Day-to-day

- Workloads: edit the relevant `kubernetes/apps/<ns>/<app>` files and push—Argo reconciles automatically. Use `make argo-sync APP=<name>` for a forced refresh.
- Secrets: update `bootstrap/central-secrets.sops.yaml` with `make secrets-edit`, then call `make secrets-apply` (or `sops -d … | kubectl apply -f -`) so External Secrets can resync.
- Cleanup/troubleshooting: `make kind-*` manages the Kind cluster, and the Make targets listed below cover the most common actions.

## Common Make targets

| Command | Purpose |
| --- | --- |
| `make bootstrap` / `bootstrap-delete` / `bootstrap-recreate` | Create or reset the Kind + Argo environment. |
| `make kind-create` / `kind-delete` / `kind-status` | Direct Kind helpers (bypass the bootstrap script). |
| `make argo-apps` / `make argo-sync APP=<name>` / `make argo-port-forward` | Inspect or interact with Argo CD. |
| `make secrets-create-key` | Generate `.sops.agekey` (prints the age recipient). |
| `make secrets-edit` / `make secrets-apply` | Edit the encrypted secret bundle and apply it to the cluster. |

Use Renovate’s PRs plus a `make bootstrap` smoke test to validate larger upgrades before merging. Update this README when bootstrap or secrets workflows change.
