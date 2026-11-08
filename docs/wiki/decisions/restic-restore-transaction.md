# Plan and guard appdata restores

Purpose: explain the restore transaction's safety boundary.
Status: current. Reviewed against: `f73a66d4d60b9fd7e373eb1cfcbde4e8df270083`.

[PR #260](https://github.com/edgard/home-ops/pull/260) retained the shared
Restic repository as the recovery source. [PR #261](https://github.com/edgard/home-ops/pull/261)
added plan-only Taskfile entry points and an Ansible role that chooses
Argo-managed appdata PVCs, excluding shared/static storage. Confirmed restores
pause app updates, stop targets, restore data, and resume policy. If a
destructive restore fails, the role leaves state for inspection rather than
silently resuming incomplete data.

The [runbook](../operations/restic-backup-restore.md) holds the operator steps.
Do not infer backup freshness from this design; inspect snapshots before
restoring. Permanent restore/rollback simulations are retired; changes to this
procedure need targeted implementation verification and review.

## Sources

- [Restore PR #261](https://github.com/edgard/home-ops/pull/261)
- [Restore planning tasks](../../../ansible/roles/restic/tasks/plan.yml)
- [Restore execution tasks](../../../ansible/roles/restic/tasks/execute.yml)
- [Restore confirmation/check-mode guards](../../../ansible/roles/restic/tasks/main.yml)

## Related pages

- [Backup and recovery](../architecture/backup-recovery.md)
- [Restic runbook](../operations/restic-backup-restore.md)
