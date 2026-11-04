# Plan and guard appdata restores

Purpose: explain the restore transaction's safety boundary.
Status: current. Reviewed against: `0eb60f6ccc54f3ad28e28fdebd0cf95ca27c1b16`.

[PR #260](https://github.com/edgard/home-ops/pull/260) retained the shared
Restic repository as the recovery source. [PR #261](https://github.com/edgard/home-ops/pull/261)
added plan-only Taskfile entry points and an Ansible role that chooses
Argo-managed appdata PVCs, excluding shared/static storage. Confirmed restores
pause app updates, stop targets, restore data, and resume policy. If a
destructive restore fails, the role leaves state for inspection rather than
silently resuming incomplete data.

The [runbook](../operations/restic-backup-restore.md) holds the operator steps.
Do not infer backup freshness from this design; inspect snapshots before
restoring.

The deployed legacy role holds child Applications and the ApplicationSet, but
does not hold the self-healing root. Its pause can therefore be undone by root
reconciliation. The [shared-data foundation](../operations/shared-data.md)
introduces a root-first fence; integration into the deployed restore entry point
belongs to the subsequent rollout stage.

## Sources

- [Restore PR #261](https://github.com/edgard/home-ops/pull/261)
- [Restore planning tasks](../../../ansible/roles/restic/tasks/plan.yml)
- [Restore execution tasks](../../../ansible/roles/restic/tasks/execute.yml)
- [Restore transaction scenarios](../../../tests/integration/test_restore.py)
- [Restore behavior fixture](../../../tests/integration/test_restore.py)

## Related pages

- [Backup and recovery](../architecture/backup-recovery.md)
- [Restic runbook](../operations/restic-backup-restore.md)
