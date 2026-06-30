# Home Ops

GitOps-driven Kubernetes homelab running on Talos Linux, managed by Argo CD with Terraform for external infrastructure and Ansible for local orchestration.

## Stack

- Talos Linux
- Kubernetes
- Argo CD
- Istio Gateway API
- External Secrets with Bitwarden
- Prometheus, Grafana, Alertmanager, and Blackbox Exporter
- Helm
- Ansible
- Terraform

## Quick Start

### Prerequisites

```bash
# Install CLI tools (macOS)
brew install python helm talosctl go-task opentofu yq yamllint shellcheck prettier yamlfmt pluto kubeconform conftest actionlint
task deps                         # Create .venv and install Ansible dependencies

# Set local operator inputs
export TALOS_NODE="192.168.1.253"
export TALOS_CLUSTER_NAME="homelab"
export TALOS_INSTALL_DISK="/dev/vda"
export KUBE_CONTEXT="admin@homelab"
export ANSIBLE_VAULT_PASSWORD="your-local-vault-password"
export BWS_ACCESS_TOKEN="your-bitwarden-secrets-manager-token"
export AWS_ACCESS_KEY_ID="your-terraform-backend-access-key"
export AWS_SECRET_ACCESS_KEY="your-terraform-backend-secret-key"
```

Keep `.envrc` for local-only operator inputs and runtime credentials; it is intentionally git-ignored.
Talos bootstrap secrets live in `ansible/roles/talos/files/secrets.vault.yml`, encrypted with Ansible Vault.
`ANSIBLE_VAULT_PASSWORD` is only needed for Talos secret generation and Vault maintenance tasks.

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
task talos:upgrade-k8s K8S_VERSION=v1.34.0  # Upgrade Kubernetes to the requested version

# Platform management
task platform:create                 # Install platform Helm releases and Argo CD root app
task platform:destroy                # Uninstall platform bootstrap components

# Argo CD
task argo:sync                       # Refresh every Argo CD application
task argo:sync app=plex              # Refresh one Argo CD application

# Vault
task vault:edit-talos                # Edit encrypted Talos bootstrap secrets

# Development
task deps                          # Create .venv and install Ansible dependencies
task fmt                           # Format all code (YAML, Terraform)
task fmt:check                     # Check formatting without modifying files
task lint:static                   # Run shellcheck and yamllint
task lint:workflows                # Validate GitHub Actions workflows
task lint:ansible                  # Run Ansible syntax, lint, and contract checks
task lint:kubernetes               # Run Kubernetes source, policy, schema, and deprecation checks
task lint:terraform                # Run backendless OpenTofu validation
task lint                          # Run the full offline validation gate
task precommit                     # Format code, then run lint

# Terraform
task tf:plan                         # Plan Terraform changes with OpenTofu
task tf:apply                        # Apply Terraform changes with OpenTofu
task tf:clean                        # Remove local Terraform cache and plan files
```

Taskfile is the operator interface; Ansible remains the orchestration implementation underneath.

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
└── terraform/              # External infrastructure (Cloudflare, Tailscale)
```

## App Metadata Convention

- `apps/<category>/<app>/app.yaml`: Argo CD ApplicationSet metadata (chart source, sync wave, optional ignore rules)
- `apps/<category>/<app>/values.yaml`: Helm values overrides for the app chart
- `apps/<category>/<app>/manifests/`: Optional raw manifests applied alongside the chart

## Contributing

Changes go through pull requests only.

Detailed contributor and agent guidance, including the validation model, testing expectations, repo conventions, and Git workflow, lives in [AGENTS.md](AGENTS.md).
