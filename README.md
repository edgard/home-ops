# Home Ops

GitOps-driven Kubernetes homelab running on Talos Linux, managed by Argo CD with Terraform for external infrastructure.

## Quick Start

### Prerequisites

```bash
# Install CLI tools (macOS)
brew install kubectl helm helmfile talosctl go-task opentofu yq bats-core yamllint shellcheck prettier yamlfmt pluto kubeconform conftest

# Set environment variables
export BWS_ACCESS_TOKEN="your-bitwarden-secrets-token"
export TALOS_NODE="192.168.1.253"
export TALOS_CLUSTER_NAME="homelab"
export TALOS_INSTALL_DISK="/dev/vda"
```

### Bootstrap Cluster

```bash
# Install and bootstrap Talos + platform
task cluster:create

# Destroy platform and reset Talos node
task cluster:destroy

# Install platform components
task platform:create

# Uninstall platform components
task platform:destroy
```

## Common Commands

```bash
# Cluster management
task cluster:create                # Install and bootstrap Talos + platform
task cluster:destroy               # Destroy platform and reset Talos node
task talos:gen                     # Generate Talos config
task talos:apply                   # Apply Talos config
task talos:bootstrap               # Bootstrap Talos control plane

# Platform management
task platform:create               # Install platform components
task platform:destroy              # Uninstall platform components

# Argo CD
task argo:sync                     # Sync all apps
task argo:sync app=plex            # Sync specific app

# Development
task fmt                           # Format all code (YAML, Terraform)
task test                          # Run behavior tests
task lint                          # Run the offline validation checks
task ci                            # Run the full CI quality gate
task precommit                     # Format code, then run the CI quality gate

# Terraform
task tf:plan                       # Plan infrastructure changes
task tf:apply                      # Apply infrastructure changes
```

## Repository Structure

```
├── apps/                   # Application definitions by category
│   ├── argocd/
│   ├── home-automation/
│   ├── kube-system/
│   ├── media/
│   ├── platform-system/
│   └── selfhosted/
├── argocd/                 # Argo CD bootstrap (root app, appsets, projects)
├── bootstrap/              # Talos + platform bootstrap
└── terraform/              # External infrastructure (Cloudflare, Tailscale)
```

## App Metadata Convention

- `apps/<category>/<app>/app.yaml`: Argo CD ApplicationSet metadata (chart source, sync wave, optional ignore rules)
- `apps/<category>/<app>/values.yaml`: Helm values overrides for the app chart
- `apps/<category>/<app>/manifests/`: Optional raw manifests applied alongside the chart

## TDD Workflow

- Script changes start with a failing Bats test under `tests/`.
- Repo behavior changes start with a failing test or compatibility check, usually `tests/*.bats` or `task lint`.
- Repo metadata and structural rules live in Conftest policy under `policy/metadata/` and are enforced by `task lint`.
- Manifest and rendered-workload guardrails live in Conftest policy under `policy/kubernetes/` and are enforced by `task lint`.
- Run `task ci` before opening or updating a PR.
- Pure formatting and mechanical version bumps can skip new tests when behavior does not change.

## Validation Model

- `task test` owns orchestration coverage only. Bats verifies dispatch, chart caching, rendered-output batching, path handling, and target-version wiring. Validator semantics live in Rego tests and the live lint gate.
- `task lint` owns direct offline validation: shellcheck, yamllint, metadata policy, raw manifest policy/schema/deprecation checks, batched rendered policy/schema/deprecation checks, and `tofu validate`.
- Metadata policy lives in `policy/metadata/`. `scripts/validate-kubernetes.sh metadata` builds the Conftest input inventory, including the cross-app fields needed for duplicate generated-name checks.
- Kubernetes policy lives in `policy/kubernetes/` and enforces repo guardrails such as required sync waves, approved route/store conventions, no `latest` image tags, and hardened defaults for app-template workloads with explicit exemptions where the repo intentionally runs as root.
- `scripts/validate-kubernetes.sh` owns the validation orchestration: Tuppr version resolution, metadata inventory generation, per-run chart caching, and batched rendered output so Conftest, kubeconform, and Pluto each run once across the rendered set.
- Policy semantics are regression-tested in `policy/metadata/*_test.rego` and `policy/kubernetes/*_test.rego`.
- `scripts/validate-kubernetes.sh` remains the compatibility entrypoint, but the supported developer surface is `task fmt`, `task test`, `task lint`, `task ci`, and `task precommit`.
- `apps/platform-system/tuppr/manifests/tuppr-kubernetes.kubernetesupgrade.yaml` is the single source of truth for the Kubernetes target version used by `kubeconform` and Pluto.

## Local And CI Flow

- `task test` runs Bats behavior regression tests for the orchestration layer.
- `task lint` runs the offline validation checks: shellcheck, yamllint, metadata policy checks (Conftest), raw manifest policy/schema/deprecation validation, batched rendered policy/schema/deprecation validation for Helm apps, and `tofu validate`.
- `task ci` runs the full quality gate by combining `task test` and `task lint`.
- `task precommit` runs `task fmt` and then `task ci`.
- GitHub Actions mirrors the local task model and runs `task ci` on pull requests.
- CI installs Conftest with `princespaghetti/setup-conftest@v1`, pinned to an explicit version that Renovate tracks alongside the other workflow tool versions.
