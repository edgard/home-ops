---
# Kubernetes Restic Restore Runbook

Purpose: operator procedure for a Kubernetes appdata restore.
Status: current. Reviewed against: `d897e58d4dbc5cd0609e9b6dc3098d88fb887639`.

The `restic` app backs up Kubernetes appdata and serves the same repository used
by the macOS and Windows workstation backups. Kubernetes owns repository
maintenance; workstations only create backup snapshots.

Use this runbook to restore Kubernetes appdata from the shared restic repo.

## Reference

| Item | Value |
| --- | --- |
| In-cluster repo | `rest:http://restic.selfhosted.svc.cluster.local:8000/` |
| Workstation repo | `rest:http://restic.edgard.org:8000/` |
| Repo storage | `/mnt/dpool/restic` |
| Appdata storage | `/mnt/spool/appdata` |
| Snapshot root | `/data/appdata` |
| PVC path | `/data/appdata/<namespace>/<pvc-name>` |
| Restore mount | `/restore/data/appdata` |

Kubernetes snapshots are selected with host `homelab`, tag `appdata`, and path
`/data/appdata`. Workstation snapshots share the repo but use different hosts
and paths:

| Host | Path | Tag |
| --- | --- | --- |
| `homelab` | `/data/appdata` | `appdata` |
| `edgards-mini` | `/Users/edgard/Documents` | `documents` |
| `edgard-desktop` | `C:\Users\Edgard\Documents` | `documents` |

The workstation entries come from the
[pre-migration runbook](https://github.com/edgard/home-ops/blob/2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b/docs/restic-backup-restore-runbook.md).
This repository does not manage those clients; verify actual snapshots before
using a workstation entry.

The backup and maintenance schedules and retention are defined in
[Restic values](../../../apps/selfhosted/restic/values.yaml); consult that file
before relying on a schedule.

## Rules

- Always preview first. Restore tasks are plan-only unless
  `confirm_restore=true` is set.
- Ansible check mode remains plan-only even when confirmation is supplied.
  The role guards both transaction entry and individual pod exec tasks because
  pod commands require an explicit check-mode guard.
- `snapshot` defaults to `latest`.
- `latest` is filtered to the Kubernetes snapshot family, so workstation
  snapshots are not eligible.
- Restore-all includes Argo-managed `nfs-fast` appdata PVCs and excludes
  shared/static storage: `media`, `restic-repo`, and `restic-appdata`.
- A confirmed restore creates a temporary `restic-restore` Job, pauses the
  `apps` ApplicationSet, disables automated sync for target apps, scales
  workloads down, deletes existing target contents under `/restore/data/appdata`,
  restores with `--exclude-xattr '*'`, resumes workloads/sync policy, and
  removes the restore Job.
- If a confirmed restore fails, inspect the data before manually resuming apps or
  clearing the restore Job.

## Restore One App

```sh
task restic:restore app=paperless
task restic:restore app=paperless confirm_restore=true
```

Use an explicit snapshot when needed:

```sh
task restic:restore app=paperless snapshot=<snapshot-id> confirm_restore=true
```

Home Assistant example:

```sh
task restic:restore app=homeassistant
task restic:restore app=homeassistant confirm_restore=true
```

The plan shows the app, namespace, source paths, restore paths, and workloads
that will be stopped and resumed. A single-PVC restore is the same command:
restore the Argo CD app that owns the PVC.

## Restore All Appdata

Before planning a confirmed restore, prepare any installed
[Sure](../apps/selfhosted/sure.md) and
[SparkyFitness](../apps/selfhosted/sparkyfitness.md) stacks for SQL recovery:

1. Record the current root Application automation, `apps` ApplicationSet policy,
   application automation, writer replica counts and backup CronJob suspension.
2. Disable root automated reconciliation, set the ApplicationSet's
   `spec.syncPolicy.applicationsSync` to `create-only`, and disable automated sync
   for these two Applications. Wait for in-flight syncs to finish.
3. Suspend their app-local backup CronJobs and wait for active backup Jobs to
   finish. Stop Sure web/worker and SparkyFitness frontend/backend/Garmin, and
   wait for their Pods to exit. Leave these writers at zero **before** the restore
   plan records replica counts. Do not manually sync either Application.
4. Select a snapshot containing each installed app's published SQL dump and
   files. A snapshot predating that app's SQL backups cannot recover its database.

These outer holds must survive the file-restore transaction: it restores the
ApplicationSet policy and replicas it recorded, so it must record `create-only`
and zero writer replicas. The root hold prevents self-heal from removing that
policy. The generic transaction clears app-owned engine directories too; they
are excluded from snapshots and initialize empty afterward.

```sh
task restic:restore-all
task restic:restore-all confirm_restore=true
```

Use an explicit snapshot when needed:

```sh
task restic:restore-all snapshot=<snapshot-id> confirm_restore=true
```

Keep the holds after file restoration. Follow each linked app's SQL import and
validation procedure with its PostgreSQL server ready and writers still stopped.
Only after validation, restore writer replicas and backup CronJob suspension,
then application automation, ApplicationSet policy and root automation last.
Verify application login and records before taking a fresh backup. On failure,
leave the affected app held for inspection.

## Cluster DR

1. Rebuild Talos/Kubernetes.
2. Restore or reattach `/mnt/dpool/restic`.
3. Recreate `/mnt/spool/appdata`.
4. Let Argo CD deploy External Secrets and `restic`.
5. Establish the SQL-app holds above before allowing their writers to start,
   then run `task restic:restore-all` first without confirmation.
6. Review the plan.
7. Run `task restic:restore-all confirm_restore=true`.
8. Import and validate Sure/SparkyFitness SQL dumps while their writers remain
   stopped; restore recorded holds in the order above.
9. Verify apps and run a fresh backup.

## CLI Fallback

Use the Ansible role for normal restores. If manual debugging is required, keep
these constraints:

- Restore into `/restore`.
- Include only paths under `/data/appdata/<namespace>/<pvc-name>`.
- Delete only contents under `/restore/data/appdata/<namespace>/<pvc-name>`.
- Use `--exclude-xattr '*'` for NFS-backed appdata.
- Filter `latest` with `--host homelab --tag appdata --path /data/appdata`.

## Sources

- [Restic deployment](../../../apps/selfhosted/restic/values.yaml)
- [Restore task entry points](../../../Taskfile.yaml)
- [Restore role](../../../ansible/roles/restic/tasks/execute.yml)
- [Restore entry point](../../../ansible/roles/restic/tasks/main.yml)
- [Restore planning role](../../../ansible/roles/restic/tasks/plan.yml)
- [Restore automation PR](https://github.com/edgard/home-ops/pull/261)

## Related pages

- [Backup and recovery architecture](../architecture/backup-recovery.md)
- [Storage](../architecture/storage.md)
