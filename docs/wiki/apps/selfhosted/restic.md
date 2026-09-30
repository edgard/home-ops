# Restic

Purpose: Restic serves the shared backup repository and runs appdata backup and maintenance jobs.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

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

The repository is a recovery dependency; successful deployment alone does not prove recent usable snapshots.

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
