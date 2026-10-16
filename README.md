# Home Ops

GitOps-driven Kubernetes homelab running on Talos Linux, managed by Argo CD with Terraform for external infrastructure and Ansible for local orchestration.

## Stack

- Talos Linux
- Kubernetes
- Argo CD
- Istio Gateway API
- External Secrets with Bitwarden
- Gatus uptime checks and Telegram alerts
- Helm
- Ansible
- Terraform

## Quick Start

### Prerequisites

```bash
# Install CLI tools (macOS)
brew install python@3.14 helm talosctl go-task opentofu yamllint prettier yamlfmt pluto kubeconform actionlint node@24
task deps                         # Install pinned validation dependencies

# Set local CLI inputs
export TALOS_NODE="192.168.1.253"
export TALOS_CLUSTER_NAME="homelab"
export TALOS_INSTALL_DISK="/dev/vda"
export KUBE_CONTEXT="admin@homelab"
```

Provision SecretSpec and BWS through your Chezmoi/Homebrew machine setup, then
store the CLI machine token once. The required SecretSpec version lives in
[the CLI role defaults](ansible/roles/cli_secrets/defaults/main.yml);
CI reads the same pin through the toolchain action:

```bash
task secrets:login
task secrets:check scope=cluster
task secrets:check scope=terraform
```

### Bootstrap Cluster

```bash
task cluster:create                  # Install Talos, bootstrap Kubernetes, then install the platform
task cluster:destroy                 # Destroy platform components, then reset the Talos node
task platform:create                 # Install platform Helm releases and Argo CD root app
task platform:destroy                # Uninstall platform bootstrap components
```

## Common Commands

```bash
# Cluster management
task cluster:create                  # Install Talos, bootstrap Kubernetes, then install the platform
task cluster:destroy                 # Destroy platform components, then reset the Talos node
task talos:gen                       # Generate Talos machine configuration
task talos:apply                     # Apply Talos machine configuration to the node
task talos:bootstrap                 # Bootstrap Kubernetes on the Talos node
task talos:upgrade                   # Upgrade Talos using the pinned role version
task talos:upgrade-k8s K8S_VERSION="${TARGET_KUBERNETES_VERSION}"  # Upgrade Kubernetes to the requested version

# Platform management
task platform:create                 # Install platform Helm releases and Argo CD root app
task platform:destroy                # Uninstall platform bootstrap components

# Argo CD
task argo:sync                       # Refresh every Argo CD application
task argo:sync app=jellyfin          # Refresh one Argo CD application

# Secrets
task secrets:check scope=cluster     # Check scoped resolution without values
task secrets:sync-cluster-token      # Update only ESO bootstrap token and verify

# Development
task deps                          # Install pinned validation dependencies
task fmt                           # Format all code (YAML, Terraform)
task fmt:check                     # Check formatting without modifying files
task lint:static                   # Run yamllint
task lint:wiki                     # Check wiki links, sources, and app coverage
task lint:workflows                # Validate GitHub Actions workflows
task lint:repository               # Check repository assertions and credential artifacts
task lint:ansible                  # Run Ansible lint plus pytest units and integration scenarios
task lint:kubernetes               # Run Kubernetes assertions and native schema/deprecation checks
task lint:terraform                # Run backendless OpenTofu validation
task test                          # Run all pytest configuration/unit/integration cases
task lint                          # Run the full offline validation gate
task precommit                     # Format code, then run lint

# Terraform
task tf:plan                         # Plan Terraform changes with OpenTofu
task tf:apply                        # Apply Terraform changes with OpenTofu
task tf:clean                        # Remove local Terraform cache and plan files
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
├── ansible/                # Local orchestration for Talos, platform, Argo, Terraform
├── tests/                  # Unified pytest configuration, unit, and integration suite
└── terraform/              # External infrastructure (Cloudflare, Tailscale)
```

## App Metadata Convention

- `apps/<category>/<app>/app.yaml`: Argo CD ApplicationSet metadata (chart source, sync wave, optional ignore rules)
- `apps/<category>/<app>/values.yaml`: Helm values overrides for the app chart
- `apps/<category>/<app>/manifests/`: Optional raw manifests applied alongside the chart

## Contributing

Changes go through pull requests only.

Start with the [knowledge wiki](docs/wiki/index.md) for system relationships and
decision history. The [Restic restore runbook](docs/wiki/operations/restic-backup-restore.md)
covers recovery. Agent and contributor guidance starts in [AGENTS.md](AGENTS.md).
