# Storage and shared media

Purpose: explain the distinct NFS-backed data paths and shared-media contract.
Status: current. Reviewed against: `0eb60f6ccc54f3ad28e28fdebd0cf95ca27c1b16`.

The NFS CSI provisioner defines the default appdata class. A separate static
media claim is mounted by several media apps; Restic repository and appdata
claims use their own storage. Appdata, shared media, and the backup repository
have different restore and ownership implications. Check the app's persistence
configuration before assuming it is included in an appdata restore.

The [shared-data foundation](../operations/shared-data.md) separates application
file generations and database dumps from live database persistence. Staging and
shared database directories need explicit capture and restore exclusions when
those services are deployed. NFS PVC requests are not dataset quotas; capacity
and stable-write behavior require separate NAS checks.

The shared-service definitions retain database and staging claims and omit
recursive fsGroup ownership changes. Their init checks require the NAS to honor
numeric UID/GID ownership. The deployed file-backup configuration and restore
eligibility explicitly exclude these infrastructure directories.

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
