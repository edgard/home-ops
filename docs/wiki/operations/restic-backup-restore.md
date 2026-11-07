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

## SparkyFitness database and files

SparkyFitness's native full archives contain a compressed SQL dump and an uploads
archive. Restic excludes the live PostgreSQL subdirectory. Restoring its PVC as
files therefore does not restore the database. For a running installation, recover
the selected completed archive into a temporary directory and use the native
administrator restore page, retaining the same Bitwarden encryption/auth secrets.

For cold recovery, use this manual application-specific sequence:

1. Recover the selected completed archive from Restic into temporary storage.
   Preserve the current data if it is still needed; do not overwrite an existing
   installation before confirming the selected archive.
2. Hold Argo reconciliation for this app using the existing maintenance procedure.
   Stop frontend, backend and Garmin; start only its dedicated PostgreSQL.
3. Use a temporary official PostgreSQL 18 client mounting the app PVC at `/data`
   and the existing app Secret for its owner credentials. Extract the outer
   archive and create the `sparky_app` LOGIN role if it is missing, leaving its
   password unset until the backend provisions it. Native dumps include grants
   to this role but do not create it. Drop/recreate only `sparkyfitness_db`, then stream the inner
   `sparkyfitness_db_backup_*.sql.gz` into `psql --set ON_ERROR_STOP=1` against that
   database. Do not use `pg_restore`: this native archive contains plain SQL.
4. Replace `/data/uploads` with the recovered uploads archive contents, preserving
   the backend's writable UID/group. Retain the API-encryption and authentication
   keys from Bitwarden. Leave the PostgreSQL files to PostgreSQL itself.
5. Remove the temporary client, resume the backend and then Garmin/frontend, and
   restore the recorded Argo settings. The backend maintains its runtime role.
   Verify login, records, upload hashes, decrypted AI/provider settings and backup
   scheduling before allowing new imports. Clean temporary recovery files.

The app's dedicated PostgreSQL owner retains the upstream privileges needed by
native restore, which drops and recreates only its own database. Do not treat a
native success response as sufficient verification: inspect SQL errors and data.
See the [app page](../apps/selfhosted/sparkyfitness.md) and
[backup implementation](https://github.com/CodeWithCJ/SparkyFitness/blob/v1.11.0/SparkyFitnessServer/services/backupService.ts).

The existing role's `restic_restore_excluded_apps` default excludes SparkyFitness
from the generic file transaction, including restore-all and cluster recovery.
Recover it with the sequence above. The generic transaction resumes its selected
apps automatically, so keep this exclusion when overriding that setting.
Other apps retain the existing file restore workflow below; the only additional
recovery configuration is this entry in the existing exclusion list.

## Restore All Appdata

```sh
task restic:restore-all
task restic:restore-all confirm_restore=true
```

Use an explicit snapshot when needed:

```sh
task restic:restore-all snapshot=<snapshot-id> confirm_restore=true
```

## Cluster DR

1. Rebuild Talos/Kubernetes.
2. Restore or reattach `/mnt/dpool/restic`.
3. Recreate `/mnt/spool/appdata`.
4. Let Argo CD deploy External Secrets and `restic`.
5. Run `task restic:restore-all` first without confirmation.
6. Review the plan.
7. Run `task restic:restore-all confirm_restore=true`.
8. Verify apps.
9. Run a fresh backup.

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
