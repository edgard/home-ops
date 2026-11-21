# Home Ops

GitOps-driven Kubernetes homelab running on Talos Linux, managed by Argo CD with Terraform for external infrastructure and Ansible for local orchestration.

## Stack

- Talos Linux
- Kubernetes
- OpenEBS ZFS LocalPV for appdata and local ZFS filesystems for shared files and backups
- [Samba guest shares for dump and media](docs/wiki/apps/selfhosted/samba.md)
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
brew install python@3.14 helm kubernetes-cli talosctl go-task opentofu uv yamlfmt pluto kubeconform actionlint shellcheck node@24
task deps                         # Synchronize locked Python dependencies and pinned collections

# Set local CLI inputs
export TALOS_NODE="192.168.1.253"
export TALOS_CLUSTER_NAME="homelab"
export TALOS_INSTALL_DISK="/dev/disk/by-id/<whole-system-ssd>"
export TALOS_INSTALL_SERIAL="<verified-system-ssd-serial>"
# If Talos exposes only the disk WWID, also set TALOS_INSTALL_WWID.
export TALOS_UPLINK_MAC="<permanent-physical-uplink-mac>"
export KUBE_CONTEXT="admin@homelab"
```

Provision SecretSpec and BWS through your Chezmoi/Homebrew machine setup, then
keep all values in one Bitwarden `home-ops` project and store its read-only machine
token once. SecretSpec uses one `bitwarden` provider; ESO reads the same project. The required SecretSpec version lives in
[the CLI role defaults](ansible/roles/cli_secrets/defaults/main.yml);
runtime checks enforce that pin. CI does not install SecretSpec:

```bash
task secrets:login
task secrets:check scope=cluster
task secrets:check scope=terraform
```

### Bootstrap Cluster

1. Prepare the [site storage](docs/wiki/architecture/storage.md#prepare-storage-for-a-talos-install).
   Identify the system SSD and uplink. Set the maintenance endpoint, its
   trusted fingerprint and the host-inspection `DEBUG_IMAGE` described in the
   bootstrap procedure. On a first install, `task cluster:create`
   bootstraps Kubernetes with pool discovery disabled. When recovering a
   control plane with an etcd snapshot, follow the recovery procedure before
   bootstrapping etcd. [Talos bootstrap](docs/wiki/architecture/talos-bootstrap.md)
2. Set `ZFS_POOL_GUID` and `ZFS_MEMBER_PARTUUIDS` from the verified pool
   inventory. Release the four member partitions, reboot
   and verify the imported datasets. Then run `task platform:foundation`.
3. With fresh etcd, use `task platform:claims` to bind the appdata
   claims before starting writers. For recovery, restore those volumes and
   verify the native database. For a first-ever install with empty appdata,
   select `PLATFORM_NEW_APPDATA=true`. Release the workloads with
   `PLATFORM_HANDOFF_CONFIRM=true task platform:handoff`. [GitOps bootstrap](docs/wiki/architecture/gitops-delivery.md)
   · [Restic recovery](docs/wiki/operations/restic-backup-restore.md)

After restoring matching etcd state, verify its existing PV/PVC bindings
against the saved inventory before resuming writers.

## Common Commands

```bash
# Cluster management
task cluster:create                  # Configure Talos and bootstrap etcd on first boot
task cluster:destroy                 # Destroy platform components, then reset the Talos node
task talos:gen                       # Generate Talos machine configuration
task talos:apply                     # Apply Talos machine configuration to the node
task talos:bootstrap                 # Bootstrap Kubernetes on the Talos node
TALOS_ZFS_RELEASE_CONFIRM="$ZFS_POOL_GUID" task talos:release-zfs  # Stage verified dpool members for reboot
task talos:upgrade                   # Upgrade Talos using the pinned role version
task talos:upgrade-k8s                # Apply the committed target manually after suspending Tuppr

# Platform management
task platform:foundation             # Install platform services and the private Restic endpoint
task platform:claims                 # Bind application storage before starting writers
PLATFORM_HANDOFF_CONFIRM=true task platform:handoff  # Verify storage and start workloads
task platform:destroy                # Uninstall platform bootstrap components

# Restic recovery previews
task restic:restore app=jellyfin       # Resolve the snapshot and destination PVC
task restic:restore-all                # Preview all supported in-place restores

# Argo CD
task argo:sync                       # Refresh every Argo CD application
task argo:sync app=jellyfin          # Refresh one Argo CD application

# Secrets
task secrets:check scope=cluster     # Check scoped resolution without values
task secrets:sync-cluster-token      # Update only ESO bootstrap token and verify

# Development
task deps                          # Synchronize locked Python dependencies and pinned collections
task fmt                           # Format YAML, Python/imports, and Terraform
task fmt:check                      # Check the same formatting without changes
task lint                          # Static analysis and backendless OpenTofu validation
task test                          # Run the small serial offline suite
task test -- validation/test_secrets.py             # Focus pytest on a path or pass normal pytest options
task check                         # Complete gate: formatting checks, lint, and tests

# Terraform
task tf:plan                         # Plan Terraform changes with OpenTofu
task tf:apply                        # Apply Terraform changes with OpenTofu
task tf:clean                        # Remove local Terraform cache and plan files
```

`task deps` requires uv and an installed Python 3.14; it never downloads Python.
Python tools are synchronized into `.venv` from `pyproject.toml` and `uv.lock`.
Formatting, checking, and testing do not install dependencies or rewrite locks.
Use `uv lock` when intentionally changing Python dependency declarations.
The [test guide](validation/README.md) describes focused lint commands and prerequisites.

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
├── validation/             # Native deployment checks and small offline tests
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
