# media-backup

Purpose: back up the persistent application claims in the media namespace.
Status: current. Reviewed against: `d80872c8700249ef67aa42919e297c37e75faef3` plus the bare-metal migration changes in this revision.

## Dependencies and data

The scheduled Restic Job mounts the claims enumerated in its values
read-only at their historical namespace/claim paths. It checks ZFS source
mounts and the expected repository ID before submitting the namespace
snapshot. Include newly provisioned application claims in these mounts.
Large shared media and the repository itself are outside this backup.

## Networking and recovery

The Job uses the internal Restic Service and namespace-scoped credentials.
Inspect Job completion, snapshot contents and a representative restore.
The ordinary restore role handles existing bound claims, and the bare-metal
runbook covers a fresh cluster before writers start.

## Sources

- [Application metadata](../../../../apps/media/media-backup/app.yaml)
- [Claim mounts and schedule](../../../../apps/media/media-backup/values.yaml)
- [Scoped credentials](../../../../apps/media/media-backup/manifests/restic-credentials.externalsecret.yaml)

## Related pages

- [Restic restore runbook](../../operations/restic-backup-restore.md)
- [Backup and recovery](../../architecture/backup-recovery.md)
