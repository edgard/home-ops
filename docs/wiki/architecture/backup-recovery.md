# Backup and recovery

Purpose: connect deployed backup resources with the operator restore procedure.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

The Restic application serves a repository and runs appdata backup and
maintenance workloads. Restore commands enter the Ansible role in plan-only
mode by default. A confirmed restore selects eligible appdata PVCs, pauses
Argo-managed updates, stops target workloads, restores data, and resumes the
original policy. Shared media and repository storage are outside the appdata
restore set. The [runbook](../operations/restic-backup-restore.md) is the
operator procedure; this page is an architectural map.

The transaction and failure behavior are documented in the
[restore decision](../decisions/restic-restore-transaction.md). A deployed
backup configuration does not prove a recent successful backup or a usable
snapshot; validate those separately before recovery work.

## Sources

- [Restic values](../../../apps/selfhosted/restic/values.yaml)
- [Restore planning tasks](../../../ansible/roles/restic/tasks/plan.yml)
- [Restore execution tasks](../../../ansible/roles/restic/tasks/execute.yml)
- [Restore Taskfile entry points](../../../Taskfile.yaml)

## Related pages

- [Storage](storage.md)
- [Restic runbook](../operations/restic-backup-restore.md)
- [Talos bootstrap](talos-bootstrap.md)
