# Storage and shared media

Purpose: explain the distinct NFS-backed data paths and shared-media contract.
Status: current. Reviewed against: `f73a66d4d60b9fd7e373eb1cfcbde4e8df270083`.

The NFS CSI provisioner defines the default appdata class. A separate static
media claim is mounted by several media apps; Restic repository and appdata
claims use their own storage. Appdata, shared media, and the backup repository
have different restore and ownership implications. Check the app's persistence
configuration before assuming it is included in an appdata restore.

The [shared-media ownership decision](../decisions/shared-media-group.md)
explains why workloads using `existingClaim: media` must preserve the shared
volume's group. The native validation data guard checks the rendered group and ownership policy.

## Sources

- [NFS provisioner values](../../../apps/kube-system/nfs-provisioner/values.yaml)
- [Media PVC](../../../apps/kube-system/nfs-provisioner/manifests/nfs-provisioner-media.persistentvolumeclaim.yaml)
- [Restic storage manifests](../../../apps/selfhosted/restic/manifests)
- [Shared-media guard](../../../validation/data.py)

## Related pages

- [Backup and recovery](backup-recovery.md)
- [Shared-media decision](../decisions/shared-media-group.md)
