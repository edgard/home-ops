# Home Ops

GitOps-driven Kubernetes homelab running on Talos Linux, managed by Argo CD with Terraform for external infrastructure.

## Quick Start

### Prerequisites

```bash
# Install CLI tools (macOS)
brew install kubectl helm helmfile talosctl go-task opentofu yq bats-core yamllint shellcheck prettier yamlfmt pluto kubeconform

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
task lint                          # Run the full quality gate

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

`Chart.yaml` is only used when authoring a local Helm chart, not for ApplicationSet metadata.

## TDD Workflow

- Script changes start with a failing Bats test under `tests/`.
- Repo behavior changes start with a failing test or compatibility check, usually `tests/*.bats` or `scripts/validate-kubernetes.sh helm-apps`.
- Repo metadata and structural rules belong in lint checks such as `scripts/validate-kubernetes.sh appset-inputs`.
- Run `task lint` while iterating and before opening or updating a PR.
- Pure formatting and mechanical version bumps can skip new tests when behavior does not change.

## Local And CI Flow

- `task lint` runs the canonical quality gate: behavior checks, static checks, Kubernetes schema validation (`kubeconform`), Helm render compatibility, and Kubernetes API deprecation checks (Pluto).
