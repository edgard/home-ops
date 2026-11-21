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

`task cluster:create` generates the machine configuration, applies it,
bootstraps fresh etcd and installs the platform foundation. For a staged
recovery, the Talos tasks can be run individually, then
`task platform:foundation` installs CSI, networking, certificates, ESO, a
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
