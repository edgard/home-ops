# Storage and shared media

Purpose: explain appdata provisioning and the two shared filesystem mounts.
Status: current. Reviewed against: `d80872c8700249ef67aa42919e297c37e75faef3`.

OpenEBS provisions a ZFS filesystem under `dpool/k8s` when a Pod first
consumes a managed claim. The default class retains the dataset after PVC
deletion. Preserve the PV handle and claim UID to identify an existing copy.
A replacement PVC receives a new UID. The single-node pool provides local
storage for Pods scheduled to this node.

Media applications share the prebound `media/media` claim. Restic uses
`selfhosted/restic-repo` for the existing backup repository. Both use local
volumes with hostname affinity. Startup checks compare the mounted dataset
and the pool identity verified on this boot. Keep the media root's expected
GID 0 and mode bits 2770 through migration. Additional permission bits may remain set. The pre-handoff mount check rejects a root that would cause kubelet to recursively change owners. Check write access, hardlinks
and Jellyfin's read-only access before resuming clients.

The source migration retains historical directories in a held snapshot.
Only app-owned appdata PVCs rendered from the current chart values are seeded.
The [cutover procedure](../operations/truenas-migration.md) includes etcd,
the original SSD, and independent repository recovery.

## Sources

- [StorageClass and shared media binding](../../../apps/kube-system/zfs-localpv/manifests)
- [CSI node guard](../../../apps/kube-system/zfs-localpv/values.yaml)
- [Restic storage manifests](../../../apps/selfhosted/restic/manifests)
- [Cold-copy operations](../../../ansible/roles/migration)
- [Shared-media validation](../../../validation/data.py)

## Related pages

- [Backup and recovery](backup-recovery.md)
- [Shared media ownership](../decisions/shared-media-group.md)
- [Storage maintenance](../apps/kube-system/storage-maintenance.md)
