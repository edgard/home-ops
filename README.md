# home-ops

Flux-managed home lab that bootstraps a Kind cluster on a remote Docker host and keeps workloads reconciled from Git.

## What's inside

- `kubernetes/flux` – Flux sources, Helm repos, image automation, notifications, and the `flux-system` namespace.
- `kubernetes/apps` – workload groups (`home-automation`, `media`, `platform`, `system`) with per-namespace `ks.yaml` files and `app/` manifests.
- `kubernetes/clusters/homelab` – bootstrap kustomization that points Flux at this repo.
- `kind/cluster-config.yaml` / `kind/bootstrap.py` – Kind cluster spec plus the end-to-end bootstrap script.

## Requirements

- Docker context on the target host named `kind-<cluster>` (the script derives the name from `kind/cluster-config.yaml`; the default is `kind-homelab`) plus CLI tools: `docker`, `kind`, `kubectl`, `flux`, `sops`, `yq`.
- Host paths `/mnt/spool` and `/mnt/dpool`, plus devices `/dev/ttyUSB0` and `/dev/net/tun`, available to every Kind node (adjust `kind/cluster-config.yaml` if your layout differs).
- Age key in `.sops.agekey` (create with `make sops-key-generate`) so Flux can decrypt secrets.
- GitHub credentials in `.git-credentials` to let Flux pull changes and push image automation commits.

## Bootstrap

1. Review `kind/cluster-config.yaml` and the Multus defaults in `kind/bootstrap.py` (`MULTUS_PARENT_*`) to ensure host mounts and network settings match your environment.
2. Encrypt required secrets with `make sops-edit TARGET=...` (see `make sops-list` for coverage).
3. Ensure a Docker context exists at `kind-<cluster>` (for example, `docker context create kind-homelab ...`).
4. Run `make bootstrap` to create the cluster, install Flux, and start reconciliation.
5. Watch progress with `make flux-status`; use `make flux-reconcile` to nudge stuck reconciliations.

## Operate the cluster

- Edit workload manifests under `kubernetes/apps/*/app`, commit, and let Flux apply on the next sync.
- Keep `.sops.agekey` handy; run `make sops-validate` to confirm secrets decrypt.
- Manage image policies in `kubernetes/flux/image-*` and tag comments (`# {"$imagepolicy": ...}`) so automation can track versions.
- Telegram alerts live in `kubernetes/flux/notifications`; set the chat ID in `provider.yaml` and keep the token encrypted at `telegram/secret.sops.yaml`.

## Handy make targets

- `make bootstrap` / `make bootstrap-destroy` – build or tear down the Kind cluster and Flux stack.
- `make flux-status` / `make flux-reconcile` – check or force reconciliations.
- `make render TARGET=<path>` / `make validate TARGET=<path>` – preview and dry-run manifests.
- `make kind-create` / `make kind-delete` – create or remove a Kind cluster using the active Docker context (local or remote).
- `make sops-*` – generate keys, edit secrets, list encrypted files, validate decryption.
