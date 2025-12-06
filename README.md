# Home Ops

Argo CD–managed Kubernetes homelab deployed onto a Kind cluster that runs on a dedicated Docker context (`kind-<cluster-name>`, default `kind-homelab`). Bootstrap, apps, and Cloudflare infra live in this repo.

## Prerequisites

- docker with a context for the cluster host (create `kind-homelab` to match `bootstrap/config/cluster-config.yaml`)
- kind, kubectl, helm
- python3 with PyYAML
- sops + age-keygen (age key stored locally at `.sops.agekey`)
- prettier, yamlfmt, yamllint
- opentofu (`tofu`) for the terraform targets
- optional: direnv to load `.envrc` for Cloudflare/B2 credentials

## Bootstrap (remote Kind)

1) Ensure a Docker context named `kind-homelab` points to the host running dockerd (e.g., `docker context create kind-homelab --docker "host=ssh://user@host"`).
2) Generate an Age key: `make secrets-create-key` (writes `.sops.agekey`).
3) Populate secrets from the template: `make secrets-edit` (SOPS edits `bootstrap/config/cluster-secrets.sops.yaml`).
4) `make bootstrap` – creates the Kind cluster from `bootstrap/config/cluster-config.yaml`, attaches workers to a macvlan network (`MULTUS_PARENT_*` env overrides supported), installs Multus and Argo CD via Helm, seeds the Argo repo secret from cluster secrets, then applies the root Argo CD app.
5) Tear down or rebuild with `make bootstrap-delete` or `make bootstrap-recreate`.

## Local Iteration

- `make kind-create | kind-delete | kind-recreate` for a local cluster using the same config.
- `make kind-status` for node status; `kubectl get pods -A` for workloads.
- `make secrets-apply` to decrypt/apply cluster secrets to the current context.
- `make argo-sync ARGOCD_SELECTOR=key=value` to force Argo refresh without the CLI.

## Repository Layout

- `bootstrap/config/` – Kind cluster config and SOPS secret template (`cluster-secrets.sops.yaml` encrypted copy).
- `bootstrap/scripts/bootstrap.py` – Kind/Multus/Argo installer that expects the `kind-<cluster>` Docker context.
- `argocd/root.app.yaml` – root Application; `argocd/namespaces/` and `argocd/projects/` define namespaces/AppProjects; `argocd/appsets/apps.appset.yaml` is the go-template ApplicationSet with RollingSync tiers.
- `apps/<group>/<app>/` – `config.yaml` (chart source/version + optional rollout/sync), `values.yaml`, and optional `manifests/` (synced directly). Groups: `argocd`, `kube-system`, `platform-system`, `ops`, `edge-services`, `media`, `home-automation`.
- `terraform/` – OpenTofu for Cloudflare DNS/rules with a Backblaze B2 S3 backend (`shadowhausterraform/homelab/terraform.tfstate`); module under `terraform/cloudflare/`.

## App Conventions

- Observability stack: Grafana (UI/alerting), VictoriaMetrics Single (Prometheus-compatible store, Grafana datasource uid/name `prometheus` via VM plugin), VictoriaLogs Single for logs (Grafana VM logs plugin), Grafana Alloy DaemonSet (scrapes cluster metrics + kube-state-metrics and remote-writes to VictoriaMetrics; ships logs to VictoriaLogs), kube-state-metrics, and Prometheus Blackbox Exporter.

- `chart.repo` is either an OCI URL (with `path: "."`) or an HTTPS repo + `name`; `chart.version` is required.
- `rollout.tier` controls the ApplicationSet RollingSync order (1 = earliest; default 10).
- `sync.serverSideApply: true` for CRDs/operators.
- Destination namespace defaults to the group directory unless overridden in `config.yaml`.
- Keep `manifests/` present even if empty; everything inside is applied.

## Dynamic Configs

Hajimari, Gatus, and Dex configs are rendered by metacontroller. Edit the CR templates under `apps/<group>/<app>/manifests/metacontroller/`; do not edit generated ConfigMaps (`*-config-generated`).

## Secrets

- Age key remains local at `.sops.agekey`; never commit decrypted secrets.
- Populate `bootstrap/config/cluster-secrets.sops.yaml` via `make secrets-edit` (template lists required fields).
- Bootstrap uses these secrets to create the Argo repo credentials and tokens for Cloudflare, OIDC, WireGuard, etc.

## Linting & Formatting

`make lint` runs prettier ➜ yamlfmt ➜ yamllint across all YAML files. Install the three binaries locally.

## Terraform / Cloudflare

- Credentials are read from environment (`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` for the B2 backend, `CLOUDFLARE_API_TOKEN`, `TF_VAR_cloudflare_zone_id`). Use `direnv allow` or `source .envrc` to load them.
- Commands: `make tf-plan`, `make tf-apply`, `make tf-validate`, `make tf-clean` (override path with `TERRAFORM_DIR=...` if needed).

## Contributing

Use Conventional Commits, run `make lint` before pushing, document any `MULTUS_PARENT_*` overrides, and note Kind/Argo validation steps in PRs. Renovate keeps chart versions current; double-check major bumps.
