# Storage and shared media

Purpose: explain the distinct NFS-backed data paths and shared-media contract.
Status: current. Reviewed against: `e66f8dac017406e0b72605aa16d5f7862aaa0c8a`.

The NFS CSI provisioner defines the default appdata class. A separate static
media claim is mounted by several media apps; Restic repository and appdata
claims use their own storage. Appdata, shared media, and the backup repository
have different restore and ownership implications. Check the app's persistence
configuration before assuming it is included in an appdata restore.

The [shared-media ownership decision](../decisions/shared-media-group.md)
explains why workloads using `existingClaim: media` must preserve the shared
volume's group. The policy tests enforce the rule in source and rendered output.

## Sources

- [NFS provisioner values](../../../apps/kube-system/nfs-provisioner/values.yaml)
- [Media PVC](../../../apps/kube-system/nfs-provisioner/manifests/nfs-provisioner-media.persistentvolumeclaim.yaml)
- [Restic storage manifests](../../../apps/selfhosted/restic/manifests)
- [Shared-media assertions](../../../tests/support/applications.py)

## Related pages

- [Backup and recovery](backup-recovery.md)
- [Shared-media decision](../decisions/shared-media-group.md)
