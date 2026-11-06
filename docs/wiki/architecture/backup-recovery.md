# Backup and recovery

Purpose: connect deployed backup resources with the operator restore procedure.
Status: current. Reviewed against: `cbcaf293696411c9289743a5882f08ead0967689`.

The Restic application serves the shared repository. Existing Restic restore
commands now enter the shared-data role in plan-only mode by default. Confirmed
operations use registered consumer scope, hold root/ApplicationSet/application
reconciliation, drain writers, restore selected databases and files, validate,
and resume recorded settings with root last. Shared infrastructure PVCs and media
are excluded from destructive file recovery. Check mode never enters the
transaction. The [runbook](../operations/restic-backup-restore.md) contains the
operator procedure; this page is an architectural map.

The transaction and failure behavior are documented in the
[restore decision](../decisions/restic-restore-transaction.md). A deployed
backup configuration does not prove a recent successful backup or a usable
snapshot; validate those separately before recovery work.

Cluster recovery also requires Bitwarden availability and an operator token;
see [secret recovery](../operations/secrets-maintenance.md). The existing Talos
identity and infrastructure values resolve from Bitwarden through scoped
SecretSpec. Protected infrastructure-state backups have a separate recovery
procedure; they do not replace Bitwarden availability.

The [shared-data coordinator](../operations/shared-data.md) uses an API-backed
Lease and journal. Capture publishes immutable checksummed generations;
a newly created upload Pod mounts that exact generation at canonical Restic
paths. Only successful, remotely verified uploads receive the canonical tag.
Capture time determines backup freshness, independently of operation health.
Unchanged consumers retain file coverage through explicit registry mappings.

The registry tracks backend and shared-service adoption separately. PostgreSQL
consumers require complete database manifests, compatible application images,
and retained encryption material. A historical file snapshot cannot replace a
PostgreSQL database. Each consumer must pass backup and recovery acceptance
before cutover. Operation schedulers remain suspended until the new orchestration
image is published, pinned, and accepted; the existing file backup continues
during this stage.

## Sources

- [Restic values](../../../apps/selfhosted/restic/values.yaml)
- [Restore planning tasks](../../../ansible/roles/shared_data/tasks/plan.yml)
- [Restore entry point](../../../ansible/playbooks/restic-restore.yml)
- [Restore execution tasks](../../../ansible/roles/shared_data/tasks/restore.yml)
- [Restore Taskfile entry points](../../../Taskfile.yaml)

## Related pages

- [Storage](storage.md)
- [Restic runbook](../operations/restic-backup-restore.md)
- [Talos bootstrap](talos-bootstrap.md)
