# Restic

Purpose: Restic serves the shared backup repository and runs appdata backup and maintenance jobs.
Status: current. Reviewed against: `20ab0bc1d62963bbe4abcb439ec491e2e9074403`.

## Dependencies

Static repository and appdata claims, Multus LAN networking, and an ExternalSecret support the workloads.

## Data and recovery

The values mount static repository and appdata claims. These are recovery
infrastructure, not ordinary app-owned claims selected by the appdata restore.
Inspect the [storage manifests](../../../../apps/selfhosted/restic/manifests)
and restore plan before changing either path.

## Networking and monitoring

The repository server uses a Multus LAN attachment and a raw DNS endpoint
manifest, rather than an app-template HTTPRoute. Check both sources before
changing how workstation clients reach the repository.

## Operational note

The repository is a recovery dependency; successful deployment alone does not
prove recent usable snapshots. Existing restore commands enter the database-aware
shared-data role. Normal retention applies repository-wide, including workstation
documents and canonical appdata, with separate host/path/tag groups preserving
consumer scopes. Its explicit `appdata-pending` keep rule protects every pending
upload from ordinary forgetting; abandoned uploads require separate inspected
cleanup.

## Sources

- [App metadata](../../../../apps/selfhosted/restic/app.yaml)
- [Helm values](../../../../apps/selfhosted/restic/values.yaml)
- [Raw manifests](../../../../apps/selfhosted/restic/manifests)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Storage](../../architecture/storage.md)
- [Restic restore transaction](../../decisions/restic-restore-transaction.md)
- [Backup and recovery](../../architecture/backup-recovery.md)
- [Restic runbook](../../operations/restic-backup-restore.md)
