# Home Ops

GitOps-driven Kubernetes homelab running on K3s, managed by Argo CD with OpenTofu for external infrastructure.

## Quick Start

### Prerequisites

```bash
# Install CLI tools
# - kubectl
# - helm
# - helmfile
# - opentofu (tofu)
# - go-task (task)
# - k3sup (https://github.com/alexellis/k3sup)

# Install k3sup
curl -sLS https://get.k3sup.dev | sh
sudo install k3sup /usr/local/bin/

# Verify k3sup installation
k3sup version

# Set environment variables
export BWS_ACCESS_TOKEN="your-bitwarden-secrets-token"
```

### Bootstrap Cluster

```bash
# Create K3s cluster on target host
task bootstrap:create TARGET_HOST=192.168.1.100

# Destroy cluster
task bootstrap:destroy TARGET_HOST=192.168.1.100

# Recreate cluster (destroy + create)
task bootstrap:recreate TARGET_HOST=192.168.1.100

# Update K3s version on existing cluster
task bootstrap:update TARGET_HOST=192.168.1.100 K3S_VERSION=v1.35.0+k3s1
```

The bootstrap process will:
1. Install K3s v1.34.3+k3s1 on target host via SSH using k3sup (Flannel CNI, ServiceLB enabled, Traefik disabled)
2. Merge kubeconfig into `~/.kube/config` with context name `homelab`
3. Deploy platform components via Helmfile (cert-manager, external-secrets, k8tz)
4. Deploy ArgoCD and sync all applications via ApplicationSet

### Configuration

Default values (can be overridden via environment variables):
- `CLUSTER_NAME`: `homelab` – Kubernetes context name in kubeconfig
- `K3S_VERSION`: `v1.34.3+k3s1` – K3s version to install
- `SSH_USER`: `root` – SSH user for target host
- `BWS_ACCESS_TOKEN`: Required for Bitwarden Secrets integration

**SSH Access**: The bootstrap script connects to the target host via SSH. Ensure:
- SSH key-based authentication is configured on the target host
- Your default SSH keys (`~/.ssh/id_rsa`, `~/.ssh/id_ed25519`, etc.) are authorized or available through ssh-agent
- The `SSH_USER` (default: `root`) has permission to install K3s

## Everyday Commands

- `task argo:sync app=name` – force Argo CD to resync Applications (omit `app` to refresh all).
- `task argo:pf` – port-forward the Argo CD server to localhost on 8080→80.
- `task lint` – prettier → yamlfmt → yamllint for YAML.
- `task tf:plan` / `task tf:apply` – manage external infrastructure via OpenTofu.

## Repo Map

- `apps/` – Application definitions grouped by category (argocd, home-automation, kube-system, media, platform-system, selfhosted). Each app contains `config.yaml` (chart source), `values.yaml`, and optional `manifests/`.
- `argocd/` – Argo CD bootstrap configuration: `root.app.yaml`, ApplicationSets, AppProjects, and Namespaces.
- `bootstrap/` – Cluster initialization scripts, K3s container configuration, and Helmfile for pre-Argo CD dependencies.
- `terraform/` – OpenTofu configuration for external infrastructure management.

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

### Incus/LXC User Namespace Mapping

When running Kubernetes in Incus/LXC containers with user namespaces, file ownership must account for UID/GID mapping.

**Container Configuration:**
- `volatile.idmap.base: "0"` – Stable mapping anchor
- Container UID 0 → Host UID 2147000001
- Container UID 568 → Host UID 568 (identity mapped)
- Container UID 1000 → Host UID 2147001001
- Container UID 569+ → Host UID 2147000570+

**Problem:** Pods fail with "Permission denied" when accessing PVCs on host-mounted storage.

**Solution:** Change file ownership on the host to match the mapped UID:

```bash
# For pods running as UID 1000 in container
ssh host "sudo chown -R 2147001001:2147001001 /path/to/data"

# For pods running as UID 0 (root) in container
ssh host "sudo chown -R 2147000001:2147000001 /path/to/data"
```

**Storage Mounts:** ZFS child datasets must be explicitly mounted in Incus:

```bash
incus config device add container-name disk2 disk \
  source=/mnt/pool/dataset \
  path=/mnt/pool/dataset
```

### USB Device Passthrough

**Problem:** Pod cannot access USB device (e.g., Zigbee coordinator at `/dev/ttyUSB0`).

**Kubernetes Limitation:** You cannot create device nodes inside containers, even with `privileged: true`. Device nodes must exist on the host.

**Solution for Incus/LXC:**

1. Verify device exists on host:
   ```bash
   ls -la /dev/ttyUSB0
   ```

2. Pass character device to container:
   ```bash
   incus config device add container-name device-name unix-char \
     source=/dev/ttyUSB0 \
     path=/dev/ttyUSB0
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
