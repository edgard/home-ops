# Home Ops agent workflow

Purpose: repository conventions for people and agents changing the homelab.
Status: current. Reviewed against: `6aed89365a1ea1eaca88216fdf9bac132a1e18e5`.
Paths in this page are relative to the repository root.

GitOps Talos Kubernetes homelab (single-node, local-only). Changes via PR only.
**Tech**: Talos • K8s • Argo CD • Istio Gateway API • External Secrets (Bitwarden) •
Gatus • Helm • Ansible • Terraform

## Build & Test

- Format: `task fmt`
- Format check: `task fmt:check`
- Dependencies: `task deps` uses Python 3.14 by default (`PYTHON_BIN` override) and installs pinned Python dependencies and Ansible collections in `.venv`
- Tests: `task test` runs all pytest configuration, unit, and isolated integration cases
- All pytest invocations use global parallel defaults capped at four workers; `PYTEST_ADDOPTS="-n 0" task test` runs serially for debugging
- Lint: `task lint` runs native format/YAML/workflow/Ansible/OpenTofu checks, then the full pytest suite once
- Focused checks: `task lint:static`, `task lint:wiki`, `task lint:workflows`, `task lint:repository`, `task lint:ansible`, `task lint:ansible:static`, `task lint:kubernetes`, `task lint:terraform`
- Local prerequisites include Node 24 or newer, OpenTofu, pinned SecretSpec, and native Kubernetes CLIs; see the [test guide](../../tests/README.md)
- Wiki check: `task lint:wiki` runs pytest checks for links, sources, index reachability, and app-page coverage
- pytest configuration assertions live in `tests/config`, adapter units in `tests/unit`, and real role/Task scenarios in `tests/integration`
- Native validators retain syntax, schema, and deprecation checks; pytest reads original sources and owns executable test discovery
- CI runs the same disjoint focused pytest subsets and requires the combined `Quality Gate`
- Pre-commit gate: `task precommit` (`task fmt` + `task lint`)
- Sync ArgoCD app: `task argo:sync [app=<name>]` (GitOps: changes must be committed and pushed to repo first)

## Developer Loop

1. Read the relevant pages from [the wiki index](index.md) and follow their
   source links before changing a repository contract.
2. Make a small change. If behavior changes, write or update the failing
   pytest contract check first.
3. Recheck affected wiki explanations. Update them in the same PR when the
   change alters their meaning; a version-only bump does not require prose
   churn. Record which pages were checked in the PR.
4. Use `task lint` while iterating when changing Ansible behavior or Helm/app
   compatibility. Run `task fmt` and `task lint` before commit or PR update.

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
- The parsed route coverage check in `tests/config/kubernetes/test_rendered.py` runs during
  `task lint:kubernetes`. Keep Jellyfin `/health` and CrossWatch `/healthz` checks.
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
  - `task lint` runs the native checks and full pytest suite once; CI partitions the same cases among focused jobs
  - Plain configuration assertions read sources directly, while isolated integration tests invoke real role entry points
  - Assert operational invariants and cross-file relationships, not duplicated versions, task names, positions, comments, or equivalent source spelling
  - Preserve runtime assertions for operator inputs and live state; offline tests supplement them
  - The [test guide](../../tests/README.md) describes fixtures and when to add a check
- `sync.wave` is required in every `apps/*/*/app.yaml` and stays within `-4` to `0`
- Kubernetes target version comes from `apps/platform-system/tuppr/manifests/tuppr-kubernetes.kubernetesupgrade.yaml`
- pytest owns the empty/private/nonsymlink Kubernetes output directory and cleanup
- The rendering fixture coordinates workers with a bounded file lock and an atomic per-run snapshot; keep resource isolation in fixtures rather than test scheduling exceptions
- A test helper invokes Helm, kubeconform, and Pluto directly, caches chart pulls per run, renders CRDs, and exports served schemas before validation. Offline wiki and Kubernetes checks have no Ansible roles or playbooks
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
2. For behavior changes, write the failing policy or repo contract check first
3. Run `task lint` before committing
4. All changes via PR only
5. Force pushes allowed only on feature branches using `--force-with-lease`

## Sources

- [Taskfile](../../Taskfile.yaml) defines the CLI commands and local gates.
- [pytest configuration](../../pyproject.toml) defines parallel defaults for all test commands.
- [Pull request workflow](../../.github/workflows/ci.yml) defines the CI jobs.
- [Pull request template](../../.github/pull_request_template.md) prompts for wiki impact.
- [ApplicationSet](../../argocd/appsets/apps.appset.yaml) defines app discovery.
- [Gatus values](../../apps/platform-system/gatus/values.yaml) and [route coverage check](../../tests/config/kubernetes/test_rendered.py) define uptime coverage.

## Related pages

- [Architecture overview](architecture/gitops-delivery.md)
- [Validation](architecture/validation.md)
- [Source catalog](sources.md)
