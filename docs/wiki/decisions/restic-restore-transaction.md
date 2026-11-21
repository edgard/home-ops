# Plan and guard appdata restores

Purpose: explain the restore transaction's safety boundary.
Status: current. Reviewed against: `d80872c8700249ef67aa42919e297c37e75faef3`.

[PR #260](https://github.com/edgard/home-ops/pull/260) retained the shared
Restic repository as the recovery source. [PR #261](https://github.com/edgard/home-ops/pull/261)
added plan-only Taskfile entry points and an Ansible role that chooses
Argo-managed appdata PVCs, excluding shared/static storage. The OpenEBS migration preserves this preview boundary and the legacy snapshot
layout. The role binds each PVC to its exact CSI dataset and resolves its
snapshot ID before changing cluster state. Per-namespace mounts follow
Kubernetes PVC ownership and allow Restic to verify the selected claim subtree.

A confirmed transaction records the previous replica and CronJob settings in
an exclusively created ConfigMap. It temporarily pauses the Argo application
controller so the root app and app children cannot restart writers, drains
scheduled consumers, and stops target workloads. Only successful restores
resume operations automatically. On failure retain the lock and inspect the
record; the [runbook](../operations/restic-backup-restore.md) describes recovery.

## Sources

- [Restore PR #261](https://github.com/edgard/home-ops/pull/261)
- [Restore planning tasks](../../../ansible/roles/restic/tasks/plan.yml)
- [Restore execution tasks](../../../ansible/roles/restic/tasks/execute.yml)
- [Restore confirmation/check-mode guards](../../../ansible/roles/restic/tasks/main.yml)

## Related pages

- [Backup and recovery](../architecture/backup-recovery.md)
- [Restic runbook](../operations/restic-backup-restore.md)
