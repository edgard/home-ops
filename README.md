# Home Ops

Kubernetes homelab managed by Argo CD and bootstrapped with Kind. GitOps-based setup where all manifests and Helm configurations live in this repo for reproducible cluster state.

## Quick Start

- Install dependencies: `python3`, `kind`, `kubectl`, `sops`, `age-keygen`, `prettier`, `yamlfmt`, `yamllint`.
- Generate an Age key: `make secrets-create-key` (stored locally at `.sops.agekey`).
- Create/edit encrypted secrets: `make secrets-edit`.
- Bootstrap cluster: `make bootstrap` (creates Kind cluster, installs Argo CD, syncs all apps).
- Tear down: `make bootstrap-delete` or rebuild: `make bootstrap-recreate`.

## Local Testing

- Create local Kind cluster: `make kind-create`; delete with `make kind-delete`.
- Apply decrypted secrets: `make secrets-apply`.
- Check cluster state: `kubectl get nodes -o wide`, `kubectl get pods -A`.
- Force Argo CD resync: `make argo-sync` (optionally scope with `ARGOCD_SELECTOR=key=value`).

## Repository Structure

### ArgoCD Pattern

- **App-of-Apps**: `argocd/root.app.yaml` bootstraps the ApplicationSet
- **Single ApplicationSet**: `argocd/appsets/apps.appset.yaml` discovers all apps via Git File Generator
- **Per-App Config**: Each app defines only what varies in `apps/*/*/config.yaml`

### Directory Layout

```
apps/                          # All applications organized by group
├── {group}/                   # e.g., platform-system, media, edge-services
│   └── {app}/                 # e.g., cert-manager, jellyfin
│       ├── config.yaml        # Minimal app config (Helm chart, sync options)
│       ├── values.yaml        # Helm values
│       └── manifests/         # Optional: additional YAML manifests
argocd/
├── root.app.yaml              # Root application (entry point)
└── appsets/
    └── apps.appset.yaml       # ApplicationSet that generates all apps
bootstrap/
├── config/
│   ├── cluster-config.yaml    # Kind cluster configuration
│   └── cluster-secrets.sops.yaml  # SOPS-encrypted secrets
└── scripts/
    └── bootstrap.py           # Automated cluster bootstrap
```

### App Configuration

Each app's `config.yaml` contains only what's necessary:

**Standard app** (OCI chart - 6 lines):

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

- **Name/Namespace**: Auto-discovered from directory path `apps/{group}/{name}`
- **Manifests**: Always included from `manifests/` directory (create empty directory for Helm-only apps)
- **Sync Wave**: Omit for default (0); use negative values (-10 to -1) for infrastructure ordering
- **Labels**: Auto-generated for grouping and filtering (part-of, component, managed-by)

## Linting & Formatting

- Format and lint: `make lint` (runs prettier, yamlfmt, yamllint)
- All YAML uses 2-space indentation
- ApplicationSet templates and config files follow consistent patterns

## Dependency Updates

- Renovate automatically updates Helm chart versions in `config.yaml` files
- Major updates require manual review; minor/patch updates auto-merge
- Kind node image updates grouped into single PR

## Contributing

- Use Conventional Commits (`feat:`, `fix:`, `refactor:`, `chore(deps):`)
- Never commit `.sops.agekey` or decrypted secrets
- Run `make lint` before committing
- In PRs: describe changes, include validation steps, note any manual follow-up actions
