# Backup and recovery

Purpose: connect deployed backup resources with the operator restore procedure.
Status: current. Reviewed against: `0347fad141d7dfe0692ab03b8636296f0921548a`.

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

Home Assistant's application owns separate configuration and Matter controller
PVCs. The app restore preview must select both; paired devices depend on the
persisted Matter fabric identity. Verify snapshot coverage before relying on it,
and preserve a compatible state backup before downgrading the server. See
[Home Assistant recovery](../apps/home-automation/homeassistant.md#data-and-recovery).

## Sources

- [Restic values](../../../apps/selfhosted/restic/values.yaml)
- [Restore planning tasks](../../../ansible/roles/restic/tasks/plan.yml)
- [Restore entry point](../../../ansible/roles/restic/tasks/main.yml)
- [Restore execution tasks](../../../ansible/roles/restic/tasks/execute.yml)
- [Restore Taskfile entry points](../../../Taskfile.yaml)
- [Home Assistant values](../../../apps/home-automation/homeassistant/values.yaml)

## Related pages

- [Storage](storage.md)
- [Restic runbook](../operations/restic-backup-restore.md)
- [Talos bootstrap](talos-bootstrap.md)
