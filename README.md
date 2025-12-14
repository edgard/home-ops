# Home Ops

Argo CD–managed Kubernetes homelab running on Kind with supporting Cloudflare DNS/edge pieces.

## Quick Start

1. Install docker, kind, kubectl, helm, python3, sops, opentofu (`tofu`), and go-task (`task`).
2. Create a Docker context that matches `bootstrap/cluster-config.yaml` (default `kind-homelab`).
3. Generate secrets: `task secrets:create-key` then `task secrets:edit`.
4. Bootstrap the cluster: `task bootstrap:create`. Tear down with `task bootstrap:destroy` (or `task bootstrap:recreate`).

## Everyday Commands

- `task secrets:apply` – decrypt/apply cluster secrets to the current kube context.
- `task argo:sync app=name` – force Argo to resync Applications (omit `app` to refresh all).
- `task argo:pf` – port-forward the Argo CD server to localhost on 8080→80.
- `task lint` – prettier → yamlfmt → yamllint for YAML.
- Cloudflare: `task tf:plan` / `task tf:apply` (env vars required: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `CLOUDFLARE_API_TOKEN`, `TF_VAR_cloudflare_zone_id`).

## Repo Map

- `bootstrap/` – Kind cluster config, SOPS secret template, helmfile, and bootstrap script.
- `bootstrap/bootstrap_kind.py` – Kind cluster bring-up and host plumbing.
- `argocd/` – root Argo app, namespaces, projects, ApplicationSet.
- `apps/<group>/<app>/` – chart config/values plus optional manifests. Groups include argocd, kube-system, local-path-storage, platform-system, ops, selfhosted, media, and home-automation.
- `terraform/` – OpenTofu for Cloudflare DNS/rules.

## More Details

This README stays high level. The full runbook, conventions, and dependency list live in `.agents.md`.
