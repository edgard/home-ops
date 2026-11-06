# Plan and guard appdata restores

Purpose: explain the restore transaction's safety boundary.
Status: current. Reviewed against: `cbcaf293696411c9289743a5882f08ead0967689`.

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

The public restore entry point now delegates to the
[shared-data coordinator](../operations/shared-data.md), which fences the
self-healing root before child policies and restores root last. Its API journal
binds selected snapshot metadata before destructive work. PostgreSQL-era restores
require database manifests, compatible images, and retained encryption keys;
selected Redis allocation recovery leaves other consumers unchanged. Historical
manifest-less recovery is restricted to file/SQLite consumers. The older file
executor rejects PostgreSQL consumers even when called directly.

The replacement orchestration image must be published and pinned before use;
paused schedulers and consumer adoption gates prevent premature rollout.
Destructive restore failures remain held, while an independent API-only watchdog
may safely recover interrupted backup pauses after fencing old actors.

## Sources

- [Restore PR #261](https://github.com/edgard/home-ops/pull/261)
- [Restore planning tasks](../../../ansible/roles/shared_data/tasks/plan.yml)
- [Restore execution tasks](../../../ansible/roles/shared_data/tasks/restore.yml)
- [Restore transaction scenarios](../../../tests/integration/test_restore.py)
- [Combined recovery scenarios](../../../tests/integration/test_data_general_restore_flow.py)

## Related pages

- [Backup and recovery](../architecture/backup-recovery.md)
- [Restic runbook](../operations/restic-backup-restore.md)
