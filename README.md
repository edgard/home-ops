# home-ops

Flux-managed home lab that bootstraps a Kind cluster on a remote Docker host and keeps workloads reconciled from Git. Flux itself is managed via the Flux Operator + Flux Instance pattern inspired by [bjw-s-labs/home-ops](https://github.com/bjw-s-labs/home-ops/).

## What's inside

- `kubernetes/flux/cluster` – root Flux `Kustomization` that fans out to every workload and injects SOPS/Helm defaults.
- `kubernetes/apps/flux-system` – Flux operator + instance HelmReleases alongside GitOps-managed Helm repositories.
- `kubernetes/apps` – workload groups (`flux-system`, `home-automation`, `media`, `web`, `platform-system`) with per-namespace `ks.yaml` files and `app/` manifests.
- `bootstrap/cluster-config.yaml` / `bootstrap/bootstrap.sh` – Kind cluster spec plus the end-to-end bootstrap script.

## Requirements

- Docker context on the target host named `kind-<cluster>` (the script derives the name from `bootstrap/cluster-config.yaml`; the default is `kind-homelab`) plus CLI tools: `docker`, `kind`, `kubectl`, `flux`, `helm`, `jq`, `sops`, `yq`.
- Host paths `/mnt/spool` and `/mnt/dpool`, plus devices `/dev/ttyUSB0` and `/dev/net/tun`, available to every Kind node (adjust `bootstrap/cluster-config.yaml` if your layout differs).
- Age key in `.sops.agekey` (create with `make sops-key-generate`) so Flux can decrypt secrets.
- GitHub credentials in `.git-credentials` so Flux can pull private Git repositories.

## Bootstrap

1. Review `bootstrap/cluster-config.yaml` and the Multus defaults in `bootstrap/bootstrap.sh` (`MULTUS_PARENT_*`) to ensure host mounts and network settings match your environment.
2. Encrypt required secrets with `make sops-edit TARGET=...` (see `make sops-list` for coverage).
3. Ensure a Docker context exists at `kind-<cluster>` (for example, `docker context create kind-homelab ...`).
4. Run `make bootstrap` to create the cluster, install the Flux operator/instance stack, and start reconciliation.
5. Watch progress with `make flux-status`; use `make flux-reconcile` to nudge stuck reconciliations.

## Operate the cluster

- Edit workload manifests under `kubernetes/apps/*/app`, commit, and let Flux apply on the next sync.
- Keep `.sops.agekey` handy; run `make sops-validate` to confirm secrets decrypt.
- Let Renovate drive container and chart upgrades; review its PRs (or the dependency dashboard) just like any other change and run `make render`/`make validate` on the touched kustomizations before merging majors.
- Flux cadence: Git sources and Kustomizations reconcile every `2h`, HelmReleases every `1h`, and OCI-backed Helm chart sources every `30m`—fast enough to pick up the daily Renovate merges without thrashing. Use `make flux-reconcile` when you need an immediate run.

## Handy make targets

- `make bootstrap` / `make bootstrap-delete` – build or tear down the Kind cluster and Flux stack.
- `make flux-status` / `make flux-reconcile` – check or force reconciliations.
- `make render TARGET=<path>` / `make validate TARGET=<path>` – preview and dry-run manifests.
- `make kind-create` / `make kind-delete` – create or remove a Kind cluster using the active Docker context (local or remote).
- `make sops-*` – generate keys, edit secrets, list encrypted files, validate decryption.

## Keep dependencies updated with Renovate

Renovate is the sole updater for this repository. It scans everything under `kubernetes/`, the Kind node images in `bootstrap/cluster-config.yaml`, GitHub Actions, and the OCI-backed Helm charts defined in each `ocirepository.yaml`. All version bumps flow through GitHub PRs and branches—Flux only consumes committed manifests.

1. Create (or reuse) a GitHub App dedicated to Renovate (GitHub → Settings → Developer settings → GitHub Apps → *New GitHub App*). Grant `Contents`, `Pull requests`, and `Issues` read/write permissions, subscribe to the *Pull request* and *Issues* events, install the App on this repo, and download the private key (`.pem`).
2. In the repo settings, add the App credentials as Actions secrets: `BOT_APP_ID` (the App’s numeric ID) and `BOT_APP_PRIVATE_KEY` (the PEM contents).
3. Kick off the “Renovate” workflow once via `Actions → Renovate → Run workflow` so it can create its first dependency dashboard; afterward it runs daily (00:00 UTC) and on config changes.

Once running, Renovate will:

- open PRs for every pinned container tag, Helm chart tag, and GitHub Action digest;
- group both `kindest/node` entries so the control-plane/worker images stay in sync;
- auto-merge every non-major update (containers, charts, GitHub Actions), so most PRs land without manual review.


Only major bumps require a manual merge; those PRs carry the `renovate/manual-review` label. Keep an eye on the dependency dashboard or the workflow logs (`Actions → Renovate`) to double-check critical upgrades; temporarily pause the workflow if you ever need to hold back a rollout.
