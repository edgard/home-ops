# Home Ops

GitOps-driven Kubernetes homelab running on Talos Linux, managed by Argo CD with Terraform for external infrastructure.

## Stack

- Talos Linux
- Kubernetes
- Argo CD
- Istio Gateway API
- External Secrets with Bitwarden
- Helm
- Terraform

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

Bitwarden bootstrap and Terraform operations require `BWS_ACCESS_TOKEN`. Terraform also needs the AWS credentials for the remote state backend.

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

## Repository Layout

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

## Contributing

Changes go through pull requests only.

Detailed contributor and agent guidance, including the validation model, testing expectations, repo conventions, and Git workflow, lives in [AGENTS.md](AGENTS.md).
