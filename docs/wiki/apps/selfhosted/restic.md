# Restic

Purpose: Restic serves the shared backup repository and runs appdata backup and maintenance jobs.
Status: current. Reviewed against: `d80872c8700249ef67aa42919e297c37e75faef3`.

## Dependencies

The server requires the prebound `restic-repo` volume, a pool identity
verified for this boot, the repository authentication file and the expected
repository ID. Multus provides the workstation-facing LAN address. Namespace
backup Jobs mount their own claims. Home automation obtains the two Restic
credential fields through a Kubernetes SecretStore restricted to the existing
Restic Secret in selfhosted.

## Data and recovery

The server exposes the `dpool/restic` filesystem and checks its
identity before opening it. The selfhosted backup reads named appdata PVCs
and preserves native SparkyFitness archives. Scheduled encrypted B2 copying
requires independent verification of a cloud snapshot and runtime approval.
See the [runbook](../../operations/restic-backup-restore.md) for enabling
the copy and recovering files.

## Networking and monitoring

The ClusterIP Service supports in-cluster clients. The Multus attachment and
DNS endpoint give workstation clients a stable repository URL.
The pre-handoff server is cluster-only and read-only. Check namespace Job
exit status, repository checks and representative cloud restores.

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
