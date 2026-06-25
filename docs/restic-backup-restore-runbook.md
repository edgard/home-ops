---
# Kubernetes Restic Restore Runbook

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

Backups run daily at `0 3 * * *`. Maintenance runs weekly at `0 4 * * 1` with
daily 14, weekly 8, monthly 12, and yearly 3 retention.

## Rules

- Always preview first. Restore tasks are plan-only unless
  `confirm_restore=true` is set.
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
