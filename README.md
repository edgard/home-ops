# Home Ops

GitOps-driven Kubernetes homelab running on Kind, managed by Argo CD with OpenTofu for external infrastructure.

## Quick Start

1. Install docker, kind, kubectl, helm, python3, opentofu (`tofu`), and go-task (`task`).
2. Create a Docker context that matches `bootstrap/cluster-config.yaml` (default `kind-homelab`).
3. Set up secrets in Bitwarden Secrets Manager with names matching the secret keys.
4. Export `BWS_ACCESS_TOKEN` environment variable with your Bitwarden machine identity token.
5. Bootstrap the cluster: `task bootstrap:create`. Tear down with `task bootstrap:destroy` (or `task bootstrap:recreate`).

## Everyday Commands

- `task argo:sync app=name` – force Argo CD to resync Applications (omit `app` to refresh all).
- `task argo:pf` – port-forward the Argo CD server to localhost on 8080→80.
- `task lint` – prettier → yamlfmt → yamllint for YAML.
- `task tf:plan` / `task tf:apply` – manage external infrastructure via OpenTofu.

## Repo Map

- `apps/` – Application definitions grouped by category (argocd, home-automation, kube-system, local-path-storage, media, platform-system, selfhosted). Each app contains `config.yaml` (chart source), `values.yaml`, and optional `manifests/`.
- `argocd/` – Argo CD bootstrap configuration: `root.app.yaml`, ApplicationSets, AppProjects, and Namespaces.
- `bootstrap/` – Cluster initialization scripts, Kind configuration, and Helmfile for pre-Argo CD dependencies.
- `terraform/` – OpenTofu configuration for external infrastructure management.
