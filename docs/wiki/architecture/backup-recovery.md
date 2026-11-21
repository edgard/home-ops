# Backup and recovery

Purpose: connect deployed backup resources with the operator restore procedure.
Status: current. Reviewed against: `09ff984c2258c4403ef203631fd580106f839e53` and this revision.

The original Restic repository stays on the retained `dpool/restic` dataset
and serves the Kubernetes cluster and existing workstation clients. Separate
CronJobs in home-automation, media and selfhosted read their concrete appdata
claims and publish namespace snapshots that retain the historical claim paths.
An explicitly approved maintenance job copies the repository to its established
encrypted B2 destination, then applies local retention on its weekly cadence.
Verify independent remote restores as described in the [runbook](../operations/restic-backup-restore.md).

The ordinary restore role resolves full snapshot IDs and bound OpenEBS
datasets before stopping consumers. A full restore compares its plan with
current Helm-rendered claim names, namespaces and owners. The runbook also
covers taking a held rollback snapshot after writers stop and before the
first in-place write. The transaction uses per-application Jobs in the
claim's namespace and restores the previous controller and scheduler state
after verified completion. Shared media and repository storage have separate
recovery paths. The [restore decision](../decisions/restic-restore-transaction.md)
records the transaction boundary. A fresh cluster without etcd prepares new OpenEBS claims before Argo starts.
The cold restore verifies the selected snapshot against each empty new
filesystem through the read-only foundation repository. Retained data can
also seed a new claim from a known held snapshot. First handoff verifies
per-claim destination evidence. [Fresh-cluster recovery](../operations/restic-backup-restore.md#new-cluster-or-lost-etcd-state)

Cluster recovery also requires Bitwarden availability and an operator token;
see [secret recovery](../operations/secrets-maintenance.md). The existing Talos
identity and infrastructure values resolve from Bitwarden through scoped
SecretSpec. Protected infrastructure-state backups have a separate recovery
procedure; they do not replace Bitwarden availability.

SparkyFitness uses its native scheduled SQL-and-uploads archives. Restic stores
those archives and uploads while excluding live PostgreSQL files. Its cold
recovery includes a database import before application writers resume; generic
file restoration alone is insufficient. The existing generic restore exclusion
list keeps this app out of automatic file-restore/resume transactions. See the
[application recovery procedure](../operations/restic-backup-restore.md#sparkyfitness-database-and-files).

## Sources

- [Restic values](../../../apps/selfhosted/restic/values.yaml)
- [Restore planning tasks](../../../ansible/roles/restic/tasks/plan.yml)
- [Fresh-claim recovery](../../../ansible/roles/restic/tasks/cold.yml)
- [Restore entry point](../../../ansible/roles/restic/tasks/main.yml)
- [Restore execution tasks](../../../ansible/roles/restic/tasks/execute.yml)
- [Restore Taskfile entry points](../../../Taskfile.yaml)

## Related pages

- [Storage](storage.md)
- [Restic runbook](../operations/restic-backup-restore.md)
- [Talos bootstrap](talos-bootstrap.md)
