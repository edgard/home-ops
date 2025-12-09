# Home Ops

Argo CD–managed Kubernetes homelab running on Kind with supporting Cloudflare DNS/edge pieces.

## Quick Start

1. Install docker, kind, kubectl, helm, python3, sops, and opentofu (`tofu`).
2. Create a Docker context that matches `bootstrap/config/cluster-config.yaml` (default `kind-homelab`).
3. Generate secrets: `make secrets-create-key` then `make secrets-edit`.
4. Bootstrap the cluster: `make bootstrap`. Tear down with `make bootstrap-delete` (or `-recreate`).

## Everyday Commands

- `make kind-create|kind-delete|kind-recreate` – local Kind cluster lifecycle.
- `make secrets-apply` – decrypt/apply cluster secrets to the current kube context.
- `make argo-sync ARGOCD_SELECTOR=key=value` – force Argo to resync selected apps.
- `make lint` – prettier → yamlfmt → yamllint for YAML.
- Cloudflare: `make tf-plan` / `make tf-apply` (env vars required).

## Repo Map

- `bootstrap/config/` – Kind cluster config and SOPS secret template.
- `bootstrap/scripts/bootstrap.py` – installer for Kind, Multus, Argo CD.
- `argocd/` – root Argo app, namespaces, projects, ApplicationSet.
- `apps/<group>/<app>/` – chart config/values plus optional manifests.
- `terraform/` – OpenTofu for Cloudflare DNS/rules.

## More Details

This README stays high level. The full runbook, conventions, and dependency list live in `.agents.md`.
