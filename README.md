# Home Ops

GitOps-driven Kubernetes homelab running on Talos Linux, managed by Argo CD with Terraform for external infrastructure.

## Quick Start

### Prerequisites

```bash
# Install CLI tools (macOS)
brew install kubectl helm helmfile talosctl go-task opentofu

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
task lint                          # Format & lint YAML

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
└── terraform/              # External infrastructure (Cloudflare)
```

## Configuration

See `AGENTS.md` for detailed configuration, conventions, and troubleshooting.
