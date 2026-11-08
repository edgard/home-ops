# Home Ops agent workflow

Purpose: repository conventions for people and agents changing the homelab.
Status: current. Reviewed against: `f73a66d4d60b9fd7e373eb1cfcbde4e8df270083`.
Paths in this page are relative to the repository root.

GitOps Talos Kubernetes homelab (single-node, local-only). Changes via PR only.
**Tech**: Talos • K8s • Argo CD • Istio Gateway API • External Secrets (Bitwarden) •
Gatus • Helm • Ansible • Terraform

## Build & Test

- Format: `task fmt`
- Format check: `task fmt:check`
- Dependencies: `task deps` uses Python 3.14 by default (`PYTHON_BIN` override) and synchronizes locked Python dependencies into `.venv` and installs pinned Ansible collections; uv never downloads Python
- Tests: `task test` runs the small serial offline suite in `validation/`
- Lint: `task lint` runs native YAML/Python/schema/workflow/Ansible/OpenTofu checks only
- Complete gate: `task check` runs formatting checks, lint, then the small offline suite once
- Focused native checks: `task lint:yaml`, `task lint:python`, `task lint:config`, `task lint:workflows`, `task lint:ansible`, `task lint:terraform`, `task lint:kubernetes`; focus pytest with `task test -- <path or options>`
- Local prerequisites include OpenTofu and native Kubernetes CLIs; SecretSpec/BWS are operator-only prerequisites; see the [test guide](../../validation/README.md)
- Wiki check: `task test -- validation/test_wiki.py` runs pytest checks for local links and app-page coverage
- Native adapters and small `test_*.py` files share `validation/`; pytest never renders charts or simulates lifecycle operations
- Native validators retain syntax, schema, and deprecation checks; pytest owns the small offline checks
- CI runs Format, Lint, and the offline Tests job and requires their combined `Quality Gate`
- Before commit: `task fmt` followed by `task check`; neither checking nor testing installs dependencies
- Sync ArgoCD app: `task argo:sync [app=<name>]` (GitOps: changes must be committed and pushed to repo first)

## Developer Loop

1. Read the relevant pages from [the wiki index](index.md) and follow their
   source links before changing a repository contract.
2. Make a small change and use targeted verification during implementation.
   Temporary tests may be extensive; remove them before merge and record results
   in the PR. Keep a permanent test only for the concrete risks in the validation
   guide, with minimal deterministic code not already covered by native tools.
3. Recheck affected wiki explanations. Update them in the same PR when the
   change alters their meaning; a version-only bump does not require prose
   churn. Record which pages were checked in the PR.
4. Use focused native checks or `task test -- <path>` while iterating. Run
   `task fmt` and `task check` before commit or PR update.

For repository questions and durable source ingests, follow the
[wiki query, ingest, and review workflow](AGENTS.md). A query starts at the
index; wiki pages guide navigation, while current configuration and tests
settle current facts.

## Project Layout

```
apps/<category>/<app>/{app.yaml,values.yaml,manifests/}
argocd/appsets/          # Auto-discovers apps/*/*/app.yaml
ansible/                 # Local orchestration, inventory, roles, role defaults, and Talos bootstrap inputs
terraform/               # Cloudflare/Tailscale infra
```

## Conventions

### App-Template v5 Structure
Order: `defaultPodOptions → controllers → service → route → persistence → configMaps`

The example below is the ordinary appdata profile. Workloads mounting the
shared media claim use the [shared-media group rule](decisions/shared-media-group.md).

```yaml
defaultPodOptions:
  securityContext:
    fsGroup: 1000
    fsGroupChangePolicy: OnRootMismatch
    runAsGroup: 1000
    runAsNonRoot: true
    runAsUser: 1000
controllers:
  main:
    annotations:
      reloader.stakater.com/auto: "true"
    replicas: 1
    strategy: Recreate
    containers:
      app:
        securityContext:
          allowPrivilegeEscalation: false
          capabilities:
            drop: [ALL]
```

### Common Annotations
- Reloader (controllers): `reloader.stakater.com/auto: "true"`

### Networking
- HTTPRoute → `gateway.platform-system.https`, hostname: `<app>.edgard.org`
- Multus LAN IP (media apps): `k8s.v1.cni.cncf.io/networks: [{"name":"multus-lan-bridge","namespace":"kube-system","ips":["192.168.1.X/24"]}]`

### Monitoring
- Gatus is the only uptime checker and Telegram alert engine. Its routed app,
  DNS, and ICMP targets are explicit in `apps/platform-system/gatus/values.yaml`.
- Review explicit Gatus targets when changing routes. Keep Jellyfin `/health`
  and CrossWatch `/healthz`; automated route-coverage assertions are retired.
- Do not add `gethomepage.dev/*` or `gatus.home-operations.com/endpoint`
  annotations to routed apps; Gatus does not use route discovery.
- Gatus uses memory storage without a PVC. There is no metrics or searchable log
  backend. A complete outage of this single node cannot trigger an alert.

### Storage
- `nfs-fast`: `/mnt/spool/appdata` (default)
- `nfs-media`: `/mnt/dpool/media` (use `existingClaim: media`)
- `nfs-restic`: `/mnt/dpool/restic`

### ArgoCD Sync Waves
`-4` CRDs → `-3` Controllers/DNS → `-2` Mesh/PVCs → `-1` k8tz → `0` Apps

### ExternalSecret Pattern
`refreshInterval → secretStoreRef (name, kind) → target → data`
Store: `external-secrets-store`

### Resource Naming
- Manifest: `{app}-{descriptor}.{kind}.yaml`
- ExternalSecret: `{app}-[{descriptor}-]credentials`
- HTTPRoute: `{app}`
- PVC: `{app}-{suffix}` or `existingClaim: media`

### Code Standards
- YAML: 2 spaces, `---` on line 1
- Field order: `apiVersion → kind → metadata → spec`
- Metadata order: `name → namespace → labels → annotations`
- Validation split:
  - Native validators own standard syntax, schema, formatting, and deprecation requirements
  - Python dependencies and tools are declared in `pyproject.toml` and locked in `uv.lock`; the supported Python range is manually managed
  - yamlfmt owns YAML formatting, Ruff owns Python/import formatting, and OpenTofu owns Terraform formatting
  - `task check` runs formatting checks, native lint, and the small offline suite once; CI uses the same commands in three jobs
  - Small offline assertions read sources directly or test production secret/schema functions; lifecycle simulations are retired
  - Assert operational invariants and cross-file relationships, not duplicated versions, task names, positions, comments, or equivalent source spelling
  - Preserve runtime assertions for operator inputs and live state; offline tests supplement them
  - The [test guide](../../validation/README.md) defines which permanent checks may remain
- `sync.wave` is required in every `apps/*/*/app.yaml` and stays within `-4` to `0`
- Kubernetes target version comes from `apps/platform-system/tuppr/manifests/tuppr-kubernetes.kubernetesupgrade.yaml`
- The native Kubernetes adapter owns a private temporary workspace and runs Helm,
  kubeconform, and Pluto serially; served CRD schemas retain precedence. No
  pytest rendering fixtures, worker locks, or shared snapshots remain.
- Ansible roles:
  - Keep operator orchestration in playbooks and roles. Task may launch native
    CLIs such as SecretSpec; role-owned adapters/plugins handle focused gaps.
    Do not reintroduce a top-level scripts workflow.
  - Role-owned defaults live in `ansible/roles/*/defaults/main.yml`; inventory vars stay limited to local/site inputs.
  - Kubernetes operations use `kubernetes.core` modules with `kube_context`; avoid adding `kubectl` tasks.
  - Runtime credentials resolve from Bitwarden through scoped SecretSpec Task commands; the CLI machine token lives in Keychain. Keep only nonsecret settings in ignored `.envrc`.
  - Talos generation uses the existing `TALOS_SECRETS_YAML` identity from SecretSpec. Recovery requires Bitwarden access; the retired Vault workflow is preserved only in history.
  - Legacy plaintext Talos secrets at `ansible/roles/talos/files/secrets.yaml` remain git-ignored and must not be reintroduced.

## Architecture Overview

GitOps homelab using ArgoCD for deployment synchronization. Apps are auto-discovered from `apps/*/*/app.yaml` metadata files. Platform services bootstrap via Ansible-managed Helm installs that read the same app metadata, infrastructure is managed through Terraform (Cloudflare DNS, Tailscale networking). Single-node cluster with local-only access via Tailscale VPN.

## External Services

- Bitwarden: one `home-ops` project with one shared read-only machine account for ESO and CLI commands; scoped SecretSpec supplies bootstrap and Terraform commands.
- Backblaze B2 S3-compatible backend: credentials supplied through the SecretSpec Terraform scope.
- Cloudflare: DNS management
- Tailscale: VPN networking (192.168.1.0/24)

## Gotchas

- Local + Tailscale only (192.168.1.0/24)
- Single-node → `replicas: 1`, `strategy: Recreate`
- s6-overlay: run as root + SETUID/SETGID; ports <1024: +NET_BIND_SERVICE
- Never commit directly to `master`

## Git Workflow

1. Branch from `master` with descriptive name
2. Verify changes during implementation; retain only justified minimal permanent checks
3. Run `task check` before committing
4. All changes via PR only
5. Force pushes allowed only on feature branches using `--force-with-lease`

## Sources

- [Taskfile](../../Taskfile.yaml) defines the CLI commands and local gates.
- [pytest configuration](../../pyproject.toml) defines the serial offline test suite.
- [Pull request workflow](../../.github/workflows/ci.yml) defines the CI jobs.
- [Pull request template](../../.github/pull_request_template.md) prompts for wiki impact.
- [ApplicationSet](../../argocd/appsets/apps.appset.yaml) defines app discovery.
- [Gatus values](../../apps/platform-system/gatus/values.yaml) define explicit uptime coverage for review.

## Related pages

- [Architecture overview](architecture/gitops-delivery.md)
- [Validation](architecture/validation.md)
- [Source catalog](sources.md)
