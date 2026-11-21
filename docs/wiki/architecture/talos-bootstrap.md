# Talos and platform bootstrap

Purpose: locate the cluster creation and upgrade boundaries.
Status: current. Reviewed against: `d80872c8700249ef67aa42919e297c37e75faef3`.

The [migration runbook](../operations/truenas-migration.md) covers the cold
source capture, SSD imaging, physical pool import and recovery. The fresh
control plane uses the existing Bitwarden Talos identity. The former VM stays
off once the physical host takes its API address.

Set `TALOS_NODE` to the final reserved address. Supply the SSD's whole-disk
`TALOS_INSTALL_DISK` by-id path, its `TALOS_INSTALL_SERIAL`, and the physical
Ethernet port's permanent `TALOS_UPLINK_MAC`. The configuration binds that
port to `br0`, preserves the bridge's DHCP reservation, and names the node
`homelab`. For first contact with the pre-flashed SSD, set
`TALOS_MAINTENANCE_NODE` to the physical NIC's distinct initial DHCP address.
Clear it after applying the machine configuration. Every apply checks the
current system disk and NIC before sending configuration. On the installed
node, the platform additionally matches the Kubernetes node's hardware UUID
and InternalIP against the authenticated Talos endpoint.

The Talos 1.14 installation selector matches both the SSD serial and its
whole-disk by-id symlink, with wiping disabled. The generated
`KubeNodeConfig` removes the control-plane scheduling taint and load-balancer
exclusion on this single node. Talos 1.14 isolates Kubernetes workloads in
their own PID and mount namespaces. The OpenEBS pool guard and maintenance
Pods use explicit host mounts and the host's ZFS extension binaries. Verify
the CSI driver can provision and mount a test volume on a sacrificial pool
during rehearsal. Host administration through
`talosctl debug --namespace inmem` uses Talos's system container runtime.

The four HDDs can stay attached during first boot. Set `DEBUG_IMAGE` to an
approved image or local archive with a shell and util-linux `nsenter`.
`task talos:apply` sends a standalone `zfs-service` configuration that sets
`ZPOOL_IMPORT_PATH=/dev/null`. It verifies the rendered service status while
Talos is still in maintenance, then submits the control plane configuration
with the same restriction. At the final authenticated address it checks the
effective setting and confirms that ZFS is unloaded or the pool list is empty.
It then loads the explicit module and verifies that the running extension
imported no pool. If the bridge switched before an interruption,
clear `TALOS_MAINTENANCE_NODE` and rerun the task.

Keep discovery disabled while inspecting the recorded pool and remapping its
filesystems. After the [storage procedure](../operations/truenas-migration.md),
export the verified `MIGRATION_POOL_GUID`, `MIGRATION_SNAPSHOT` and
`MIGRATION_SNAPSHOT_GUID`. Run
`TALOS_ZFS_RELEASE_CONFIRM="$MIGRATION_POOL_GUID" task talos:release-zfs`.
It checks the live pool, held snapshot and mount properties, then stages an
import path containing the four member partition UUIDs. Keep writers stopped
for the planned reboot. Verify the remounted pool and datasets before
starting the foundation. Routine applies preserve the current discovery
policy and stop if a different machine configuration is already staged.
A pool member replacement changes its partition UUID. Update the verified
import path as part of disk replacement before depending on the next reboot.

`task cluster:create` generates and applies the machine configuration and
bootstraps fresh etcd. If interrupted before writing kubeconfig, rerun
`task talos:bootstrap` with the same target environment. It resumes from a
healthy local member and verifies Talos health, the member ID, voting status
and advertised endpoints before issuing credentials. A nonempty etcd
directory by itself cannot satisfy these checks.

Cluster creation holds the platform while ZFS discovery is disabled.
With the four-member policy active it continues to the foundation. For a
staged recovery, run the Talos tasks individually. After accepting the cold
boot, `task platform:foundation` checks that the released member policy is
active with no pending machine configuration, then installs CSI, networking, certificates, ESO, a
private read-only Restic server and Argo CD. Set `MIGRATION_POOL_GUID` to the
source-recorded dpool GUID on first foundation bootstrap. The immutable storage
identity preserves that GUID and the boot SSD by-id path across reruns.
The temporary Restic server verifies the existing repository ID and lists its
snapshots through authenticated cluster DNS. It shares the eventual GitOps
Deployment and Service names so restored workloads can take over in place.

Restore the claims and verify their contents before running
`PLATFORM_HANDOFF_CONFIRM=true task platform:handoff`. Handoff checks the
per-claim receipts and dataset mounts, records the merged revision, pool and snapshot in an
immutable ConfigMap, then applies the root Application. A later foundation
run leaves the GitOps-owned Restic server in place. Root reconciliation and
ApplicationSet ownership have a 300-second deadline, followed by 600 seconds
for fresh application secrets. See the
[maintenance and recovery runbook](../operations/secrets-maintenance.md)
for external credentials.

The [Image Factory installer decision](../decisions/talos-image-factory.md)
covers the RAW image and installer. Take a restricted etcd snapshot before a
live Talos upgrade. The upgrade checks physical/Kubernetes identity and mounted
datasets, drains the node and keeps it cordoned across reboot. After validating
the server version and the returned pool and mounts, the role releases the
cordon. A failed check leaves scheduling paused for investigation.

Platform preflight keeps the GitHub identity endpoint in the nonsecret
`platform_repository_identity_url` role default. CLI commands use the GitHub
endpoint; permanent loopback bootstrap simulations are retired.

Platform removal forwards `platform_helm_timeout` through `wait_timeout`: the
pinned Kubernetes collection's uninstall path does not forward its preferred
`timeout` parameter. Collection upgrades require targeted verification of
uninstall waiting and failure propagation; no permanent CLI simulation remains.

## Sources

- [CLI secret contract](../../../secretspec.toml)
- [First-boot ZFS restriction](../../../ansible/roles/talos/tasks/preseed_zfs.yml) and [four-member release](../../../ansible/roles/talos/tasks/release_zfs.yml)
- [Physical target checks](../../../ansible/roles/talos/tasks/target.yml)
- [Private repository bootstrap](../../../ansible/roles/platform/tasks/restic_server.yml)
- [GitOps release](../../../ansible/roles/platform/tasks/release_root.yml)
- [Maintenance runbook](../operations/secrets-maintenance.md)

- [Talos role defaults](../../../ansible/roles/talos/defaults/main.yml)
- [Talos generation tasks](../../../ansible/roles/talos/tasks/generate.yml)
- [Talos upgrade tasks](../../../ansible/roles/talos/tasks/upgrade.yml)
- [Platform bootstrap tasks](../../../ansible/roles/platform/tasks/bootstrap.yml)
- [Operator tasks](../../../Taskfile.yaml)

## Related pages

- [GitOps delivery](gitops-delivery.md)
- [Backup and recovery](backup-recovery.md)
- [Secrets](secrets.md)
