# Home Ops

Kubernetes homelab managed by Argo CD (app-of-apps) and bootstrapped with Kind. Everything needed to recreate the cluster lives in this repo.

## Quick Start

- Install dependencies: `docker`, `python3`, `kind`, `kubectl`, `helm`, `sops`, `age-keygen`, `yamlfmt`, `yamllint`.
- Generate an Age key: `make secrets-create-key` (stored locally at `.sops.agekey`).
- Create or edit encrypted secrets: `make secrets-edit` (starts from `bootstrap/config/cluster-secrets.template.yaml`).
- Bootstrap cluster: `make bootstrap` (uses `bootstrap/config/cluster-config.yaml`, installs Argo CD, syncs all apps).
- Tear down or rebuild: `make bootstrap-delete` or `make bootstrap-recreate`.

## Local Testing

- Create local Kind cluster: `make kind-create`; delete with `make kind-delete`.
- Apply decrypted secrets: `make secrets-apply`.
- Check cluster state: `kubectl get nodes -o wide`, `kubectl get pods -A`.
- Force Argo CD resync: `make argo-sync` (optionally scope with `ARGOCD_SELECTOR=key=value`).
- Lint manifests: `make lint` (yamlfmt then yamllint).

## Repository Structure

### Argo CD Layout

- `argocd/root.app.yaml` is the entrypoint; it applies `argocd/namespaces/*.namespace.yaml` and the ApplicationSet.
- `argocd/appsets/apps.appset.yaml` is a go-template ApplicationSet that discovers `apps/*/*/config.yaml` via the Git generator.

### Apps Directory

- `apps/{group}/{app}/config.yaml` declares the Helm chart source, targetRevision, and optional sync settings.
- `apps/{group}/{app}/values.yaml` contains the chart values for that app.
- `apps/{group}/{app}/manifests/` holds any extra YAML (CRDs, metacontroller templates, routes, etc.).
- Namespaces follow the group name (edge-services, platform-system, ops, media, home-automation, arc, argocd).

### Bootstrap Assets

- `bootstrap/config/cluster-config.yaml` Kind config that sets the cluster name and node image.
- `bootstrap/config/cluster-secrets.template.yaml` starting point for SOPS-managed secrets; encrypted copy lives at `cluster-secrets.sops.yaml`.
- `bootstrap/scripts/bootstrap.py` provisions Kind, installs Argo CD, and syncs apps. It honors `MULTUS_PARENT_IFACE`, `MULTUS_PARENT_SUBNET`, `MULTUS_PARENT_GATEWAY`, and `MULTUS_PARENT_IP_RANGE` environment overrides.

### App Configuration Patterns

Each app's `config.yaml` contains only what's necessary:

**OCI Helm repo**:

```yaml
helm:
  repoURL: oci://ghcr.io/bjw-s-labs/helm/app-template
  path: .
  targetRevision: 4.4.0
```

**HTTPS Helm repo**:

```yaml
helm:
  repoURL: https://kubernetes-sigs.github.io/external-dns
  chart: external-dns
  targetRevision: 1.19.0
```

**Infrastructure app** (with sync ordering):

```yaml
helm:
  repoURL: oci://ghcr.io/argoproj/argo-helm/argo-cd
  path: .
  targetRevision: 9.1.4
syncWave: "-10" # Deploy before other apps
syncPolicy:
  serverSideApply: true # Required for CRDs
```

### Conventions

- Application name comes from the app directory; destination namespace defaults to the group directory unless overridden in `config.yaml`.
- Additional manifests under `manifests/` are always synced; keep the directory present even if empty.
- Use `syncWave` (negative for infrastructure-first ordering) and `syncPolicy.serverSideApply` when CRDs are involved.
- Labels are generated for name, part-of, component, and managed-by to simplify filtering.

### Dynamic Configs (Metacontroller)

Hajimari, Gatus, and Dex configs are rendered by metacontroller CompositeControllers under each app's `manifests/metacontroller/`. Edit the CR templates there; do not edit generated ConfigMaps (`hajimari-config-generated`, `gatus-config-generated`, `dex-config-generated`).

## Linting & Formatting

- `make lint` runs yamlfmt then yamllint.
- YAML uses 2-space indentation; keep fields ordered logically (metadata → spec/values).

## Secrets

- Age key stays local at `.sops.agekey`; do not commit it or decrypted secrets.
- `make secrets-edit` uses SOPS to manage `bootstrap/config/cluster-secrets.sops.yaml`.
- `make secrets-apply` decrypts and applies secrets to the current cluster.

## Dependency Updates

- Renovate (`.github/workflows/renovate.yaml`, `.renovaterc.json5`) updates chart versions in `config.yaml` and other dependencies; review major bumps.

## Contributing

- Use Conventional Commits (`feat:`, `fix:`, `refactor:`, `chore(deps):`).
- Run `make lint` before committing and include validation steps (Kind/Argo checks) in PRs.
- Document any bootstrap env overrides (e.g., `MULTUS_PARENT_*`) used during changes.
