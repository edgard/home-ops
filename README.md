# Home Ops

GitOps-driven Kubernetes homelab running on k3d (K3s in Docker), managed by Argo CD with Terraform for external infrastructure.

## Quick Start

### Prerequisites

```bash
# Install CLI tools (macOS)
brew install kubectl helm helmfile k3d docker go-task opentofu

# Set environment variables
export BWS_ACCESS_TOKEN="your-bitwarden-secrets-token"
export DOCKER_HOST="ssh://user@host.local"
```

### Bootstrap Cluster

```bash
# Create cluster
task bootstrap:create

# Destroy cluster
task bootstrap:destroy

# Recreate cluster
task bootstrap:recreate
```

## Common Commands

```bash
# Cluster management
task bootstrap:create              # Create cluster
task bootstrap:destroy             # Destroy cluster

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
├── bootstrap/              # Cluster initialization (k3d, helmfile)
└── terraform/              # External infrastructure (Cloudflare, Tailscale)
```

## Architecture

**Cluster**: k3d (K3s in Docker) on remote TrueNAS Scale host  
**Access**: VPN-only via Tailscale (no public exposure)  
**Ingress**: Istio Gateway API  
**Storage**: local-path-provisioner (SSD: `local-fast`, HDD: `local-bulk`)  
**Secrets**: Bitwarden Secrets Manager via External Secrets Operator  
**DNS**: Split-horizon (Cloudflare public, Unifi internal)  

## Configuration

See `AGENTS.md` for detailed configuration, conventions, and troubleshooting.
