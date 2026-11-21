# media-backup

Purpose: back up the persistent application claims in the media namespace.
Status: current. Reviewed against: `e0ffdb032870a9272c7abd691788e9b4e4b48ee1` and this revision.

## Dependencies and data

The scheduled Restic Job mounts the claims enumerated in its values
read-only at their namespace and claim paths. It checks ZFS source
mounts and the expected repository ID before submitting the namespace
snapshot. Include newly provisioned application claims in these mounts.
Large shared media and the repository itself are outside this backup.

## Networking and recovery

The Job uses the internal Restic Service and namespace-scoped credentials.
Inspect Job completion, snapshot contents and a representative restore.
Use the Restic runbook to recover an existing claim or populate new claims
before starting workloads on a rebuilt cluster.

## Sources

- [Application metadata](../../../../apps/media/media-backup/app.yaml)
- [Claim mounts and schedule](../../../../apps/media/media-backup/values.yaml)
- [Scoped credentials](../../../../apps/media/media-backup/manifests/restic-credentials.externalsecret.yaml)

## Related pages

- [Restic restore runbook](../../operations/restic-backup-restore.md)
- [Backup and recovery](../../architecture/backup-recovery.md)
