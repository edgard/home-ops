# Backup and recovery

Purpose: connect deployed backup resources with the operator restore procedure.
Status: current. Reviewed against: `0eb60f6ccc54f3ad28e28fdebd0cf95ca27c1b16`.

The Restic application serves a repository and runs appdata backup and
maintenance workloads. Restore commands enter the Ansible role in plan-only
mode by default. A confirmed restore selects eligible appdata PVCs, pauses
Argo-managed updates, stops target workloads, restores data, and resumes the
original policy. Shared media and repository storage are outside the appdata
restore set. Check mode never enters the restore transaction, including when
confirmation is supplied. The [runbook](../operations/restic-backup-restore.md) is the
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

The [shared-data foundation](../operations/shared-data.md) introduces an API-backed
maintenance journal and database-aware capture/recovery adapters. Its registry
tracks adoption separately from the existing file-backup path. Each PostgreSQL
consumer must pass backup and restore acceptance before its cutover; the first
foundation stage leaves the deployed file-backup workflow in place. The prepared
shared-service PVCs and staging area are explicitly excluded from generic file
capture and destructive restoration. Their operation schedulers stay suspended
until database-aware recovery is accepted.

## Sources

- [Restic values](../../../apps/selfhosted/restic/values.yaml)
- [Restore planning tasks](../../../ansible/roles/restic/tasks/plan.yml)
- [Restore entry point](../../../ansible/roles/restic/tasks/main.yml)
- [Restore execution tasks](../../../ansible/roles/restic/tasks/execute.yml)
- [Restore Taskfile entry points](../../../Taskfile.yaml)

## Related pages

- [Storage](storage.md)
- [Restic runbook](../operations/restic-backup-restore.md)
- [Talos bootstrap](talos-bootstrap.md)
