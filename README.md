# Home Ops

GitOps-driven Kubernetes homelab running on k3d (K3s in Docker), managed by Argo CD with OpenTofu for external infrastructure.

## Quick Start

### Prerequisites

```bash
# Install CLI tools (macOS)
brew install kubectl helm helmfile k3d docker go-task opentofu

# Set environment variables
export BWS_ACCESS_TOKEN="your-bitwarden-secrets-token"
```

### Bootstrap Cluster

```bash
# Create k3d cluster on remote TrueNAS Docker
DOCKER_HOST_SSH=user@host BWS_ACCESS_TOKEN=xxx ./bootstrap/bootstrap-k3d.sh create

# Destroy cluster
DOCKER_HOST_SSH=user@host ./bootstrap/bootstrap-k3d.sh destroy

# Recreate cluster (destroy + create)
DOCKER_HOST_SSH=user@host BWS_ACCESS_TOKEN=xxx ./bootstrap/bootstrap-k3d.sh recreate
```

The bootstrap process will:
1. Resolve Docker host IP from SSH hostname
2. Create Docker context and connect to remote TrueNAS Docker via SSH
3. Verify storage paths and USB device exist on host
4. Create k3d cluster with 1 server (control plane) and 1 agent (worker)
5. Configure k3d with:
   - K3s version: v1.33.6+k3s1 (Traefik disabled)
   - API server exposed at `<docker-host-ip>:6443`
   - Load balancer ports: 8080:80, 8443:443 (host:container)
   - Storage mounts on agent: `/mnt/spool/appdata`, `/mnt/dpool/media`, `/mnt/dpool/kopia-repo`
   - USB device on agent: `/dev/ttyUSB0` (Zigbee coordinator)
6. Configure kubeconfig with context name `k3d-homelab`
7. Deploy platform components via Helmfile (cert-manager, external-secrets, local-path-provisioner)
8. Deploy ArgoCD and sync all applications via ApplicationSet

### Configuration

**Required environment variables:**
- `DOCKER_HOST_SSH` – SSH connection to Docker host (e.g., `user@host.local` or `user@192.168.1.254`)
- `BWS_ACCESS_TOKEN` – Bitwarden Secrets Manager token (create/recreate only)

**Optional environment variables:**
- `CLUSTER_NAME` – Cluster name (default: `homelab`)
- `K3S_VERSION` – K3s version (default: `v1.33.6+k3s1`)

**Host requirements:**
- SSH key-based authentication to Docker host
- Docker daemon running and accessible via SSH
- Storage paths exist: `/mnt/spool/appdata`, `/mnt/dpool/media`, `/mnt/dpool/kopia-repo`
- USB Zigbee coordinator at `/dev/ttyUSB0` (optional, for home automation)

## Everyday Commands

```bash
# Bootstrap cluster
task bootstrap:create DOCKER_HOST_SSH=user@host BWS_ACCESS_TOKEN=xxx

# Destroy cluster  
task bootstrap:destroy DOCKER_HOST_SSH=user@host

# Recreate cluster
task bootstrap:recreate DOCKER_HOST_SSH=user@host BWS_ACCESS_TOKEN=xxx

# Force Argo CD to resync applications
task argo:sync              # Sync all applications
task argo:sync app=plex     # Sync specific application

# Port-forward Argo CD UI
task argo:pf                # Access at http://localhost:8080

# Format and lint YAML files
task lint

# Manage external infrastructure
task tf:plan
task tf:apply
```

## Repo Map

- `apps/` – Application definitions grouped by category (argocd, home-automation, kube-system, media, platform-system, selfhosted). Each app contains `config.yaml` (chart source), `values.yaml`, and optional `manifests/`.
- `argocd/` – Argo CD bootstrap configuration: `root.app.yaml`, ApplicationSets, AppProjects, and Namespaces.
- `bootstrap/` – Cluster initialization scripts and Helmfile for pre-Argo CD dependencies (cert-manager, external-secrets, local-path-provisioner).
- `terraform/` – OpenTofu configuration for external infrastructure management (Cloudflare DNS, Tailscale).

## Architecture

### k3d Cluster Structure

The cluster runs on a remote Docker host (TrueNAS Scale) via k3d:

**Nodes:**
- **1 Server (Control Plane):** `k3d-homelab-server-0`
  - Runs Kubernetes control plane components
  - API server exposed at `<docker-host-ip>:6443`
  
- **1 Agent (Worker):** `k3d-homelab-agent-0`
  - Runs application workloads
  - Has access to storage mounts and USB devices

**Load Balancer:** `k3d-homelab-serverlb`
  - Proxies traffic to the cluster
  - Host ports 8080/8443 → Container ports 80/443

**Storage:**
- `local-fast` StorageClass (default) → `/mnt/spool/appdata` (SSD)
- `local-bulk` StorageClass → `/mnt/dpool` (HDD, for media)
- Managed by `local-path-provisioner` with automatic PVC provisioning

**Networking:**
- Istio Gateway for ingress (replaces Traefik)
- Multus for secondary macvlan networks (optional DHCP)
- Gateway exposed via load balancer on ports 8080/8443

## Troubleshooting

### Security Contexts and Permissions

**s6-overlay Images (LinuxServer.io, Plex, etc.)**

Many container images use [s6-overlay](https://github.com/just-containers/s6-overlay) for process supervision. These images require running as root initially to properly drop privileges to the configured `PUID`/`PGID`.

**Problem:** Pod crashes with "Permission denied" errors on s6 scripts.

**Solution:** Remove `runAsNonRoot: true`, `runAsUser`, and `runAsGroup` from the pod's `securityContext`. The image will handle privilege dropping internally.

```yaml
defaultPodOptions:
  securityContext:
    fsGroup: 1000
    fsGroupChangePolicy: OnRootMismatch
    # Remove: runAsNonRoot, runAsUser, runAsGroup
```

**Examples:** Plex, qBittorrent (LinuxServer images)

**Init Containers Requiring Root**

Init containers may need different security contexts than main containers to perform privileged operations.

**Problem:** Init container fails with "Permission denied" when running system commands like `apt-get`, `chown`, etc.

**Solution:** Override security context for specific init containers:

```yaml
initContainers:
  setup:
    securityContext:
      runAsUser: 0
      runAsGroup: 0
      runAsNonRoot: false
```

**Example:** Paperless tesseract-langs init container (`apps/selfhosted/paperless/values.yaml:18-27`)

### k3d Storage and Permissions

With k3d, storage is straightforward because Docker bind mounts use host UIDs directly:

**Storage Paths:**
- `/mnt/spool/appdata` – Fast SSD storage (local-fast StorageClass)
- `/mnt/dpool/media` – Bulk HDD storage (local-bulk StorageClass)
- `/mnt/dpool/kopia-repo` – Backup repository

**How it works:**
1. k3d mounts host paths into the agent container
2. `local-path-provisioner` creates subdirectories in mounted paths
3. Files are created with the pod's UID/GID, which maps directly to host UIDs
4. No UID mapping complexity (unlike Incus/LXC)

**Problem:** Pod fails with "Permission denied" when accessing PVC storage.

**Solution:** Ensure the host directory is accessible and check ownership:

```bash
ssh $DOCKER_HOST_SSH "ls -la /mnt/spool/appdata/<namespace>/<pvc-name>"
# Files should be owned by the UID/GID specified in pod securityContext
```

### USB Device Passthrough (k3d)

USB devices are passed through to the k3d agent node and then mounted in pods.

**Problem:** Pod cannot access USB device (e.g., Zigbee coordinator at `/dev/ttyUSB0`).

**How k3d handles USB devices:**
1. k3d cluster creation includes: `--volume "/dev/ttyUSB0:/dev/ttyUSB0@agent:*"`
2. Device is available inside agent container at `/dev/ttyUSB0`
3. Pods mount it using hostPath

**Solution:**

1. Verify device exists on Docker host:
   ```bash
   ssh $DOCKER_HOST_SSH "ls -la /dev/ttyUSB0"
   ```

2. Verify device is in k3d agent container:
   ```bash
   docker exec k3d-homelab-agent-0 ls -la /dev/ttyUSB0
   ```

3. Mount in pod as hostPath:
   ```yaml
   persistence:
     usb:
       type: hostPath
       hostPath: /dev/ttyUSB0
       hostPathType: CharDevice
       globalMounts:
         - path: /dev/ttyUSB0
   ```

**Note:** With k3d, device passthrough is configured at cluster creation time via `--volume` flag. No manual device configuration needed (unlike Incus `unix-char` devices).

**Example:** Zigbee2MQTT (`apps/home-automation/zigbee2mqtt/values.yaml:73-78`)

### Multus Network Issues

**Problem:** Pod stuck with "address already in use" or "no more tries" errors when using macvlan with DHCP.

**Common Causes:**
- Stale DHCP lease for MAC address
- DHCP pool exhausted
- Another device using the same MAC address

**Solution:**
- Check DHCP server for conflicting leases
- Release/delete stale leases for the MAC address
- Verify DHCP pool has available addresses
- Ensure MAC addresses are unique across all pods
