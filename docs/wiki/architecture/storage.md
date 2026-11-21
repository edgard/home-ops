# Storage and shared media

Purpose: explain appdata provisioning and the two shared filesystem mounts.
Status: current. Reviewed against: `50dc84a27f19eac0ca5d644abdeccc2d4383bc48` and this revision.

OpenEBS provisions a ZFS filesystem under `dpool/k8s` when a Pod first
consumes a managed claim. The default class retains the dataset after PVC
deletion. Preserve the PV handle and claim UID to identify an existing copy.
A replacement PVC receives a new UID. The single-node pool provides local
storage for Pods scheduled to this node.

Media applications share the prebound `media/media` claim. Restic uses
`selfhosted/restic-repo` for the existing backup repository. Both use local
volumes with hostname affinity. Startup checks compare the mounted dataset
and the pool identity verified on this boot. The media root requires GID 0
and mode bits 2770 so kubelet can mount it without recursively changing
ownership. Keep downloads and the media library on this same filesystem
for hardlinks. Jellyfin consumes the media library read-only.

Save an off-node etcd snapshot and the matching Talos identity to recover
existing PVC/PV records. Keep an independent copy of the Restic repository
for recovery if the pool is lost. On a rebuilt control plane, verify the
actual bound datasets before starting applications. The [Restic runbook](../operations/restic-backup-restore.md)
covers recovery of namespace backups and application-native databases.
The [Samba service](../apps/selfhosted/samba.md) mounts the media and dump
filesystems directly from its own namespace. Its startup checks the pool marker
and each ZFS mount before allowing LAN guests to write. These shared datasets
need independent backups.

## Prepare storage for a Talos install

Bootstrap expects a prepared pool named `dpool` with four identified data
partitions on separate HDDs, and a separate Talos system SSD. Keep the pool
GUID and each member's GPT PARTUUID in the private site inventory. The Talos
role checks them before enabling automatic import. On a replacement control
plane, reuse the existing filesystems, repository and credentials.

| ZFS filesystem | Mountpoint | Used by |
| --- | --- | --- |
| `dpool` | `/var/mnt/dpool` | Talos host |
| `dpool/k8s` | `none` | OpenEBS creates each claim's filesystem below this parent |
| `dpool/dump` | `/var/mnt/dpool/dump` | File services on the LAN |
| `dpool/media` | `/var/mnt/dpool/media` | Prebound shared media PV |
| `dpool/restic` | `/var/mnt/dpool/restic` | Prebound backup repository PV |

Foundation verifies the media and repository mounts. Samba verifies its two
exported mounts when the pod starts.

For a site built on empty disks, prepare this layout on the verified storage
host. Use POSIX ACLs and extended attributes on the OpenEBS parent
(`acltype=posixacl`, `xattr=sa`). The host-mounted filesystems use
`canmount=on`. Disable ZFS NFS and SMB sharing. Inspect the effective
properties with `zfs list -r -o name,canmount,mountpoint,sharenfs,sharesmb dpool`
and record the GUID with `zpool get -Hp -o value guid dpool` before exporting
the pool for Talos. [OpenZFS dataset creation](https://openzfs.github.io/openzfs-docs/man/master/8/zfs-create.8.html)

At a **new site with an empty backup dataset**, initialize the repository on
the mounted `dpool/restic` with `restic init --repo /var/mnt/dpool/restic`.
Store the password as `restic_server_password` in Bitwarden. Use
`restic -r /var/mnt/dpool/restic cat config` to obtain the full ID for
`restic_repository_id`, and create a bcrypt `.htpasswd` for user `restic`
with that password on the same dataset. During recovery, attach the known
repository or restore its mirror with the original HTTP authentication file.
[Restic repository initialization](https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html)
· [Backup and restore](../operations/restic-backup-restore.md)

## Sources

- [StorageClass and shared media binding](../../../apps/kube-system/zfs-localpv/manifests)
- [CSI node guard](../../../apps/kube-system/zfs-localpv/values.yaml)
- [Restic storage manifests](../../../apps/selfhosted/restic/manifests)
- [Storage verification and bootstrap](../../../ansible/roles/platform/tasks)
- [Restic restore role](../../../ansible/roles/restic)
- [Shared-media validation](../../../validation/data.py)

## Related pages

- [Backup and recovery](backup-recovery.md)
- [Shared media ownership](../decisions/shared-media-group.md)
- [Storage maintenance](../apps/kube-system/storage-maintenance.md)
