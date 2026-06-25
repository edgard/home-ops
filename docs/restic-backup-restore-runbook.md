---
# Shared Restic Backup And Restore Runbook

The `restic` app backs up Kubernetes appdata and serves the same repository used
by the macOS and Windows workstation backups. Kubernetes owns repository
maintenance; workstations only create backup snapshots.

Use this runbook when restoring Kubernetes appdata from the shared restic repo.

## Facts

| Item | Value |
| --- | --- |
| In-cluster repo | `rest:http://restic.selfhosted.svc.cluster.local:8000/` |
| Workstation repo | `rest:http://restic.edgard.org:8000/` |
| Repo storage | `/mnt/dpool/restic` |
| Appdata storage | `/mnt/spool/appdata` |
| Snapshot root | `/data/appdata` |
| PVC path | `/data/appdata/<namespace>/<pvc-name>` |
| Restore mount | `/restore/data/appdata` |

Auth uses `RESTIC_REST_USERNAME`, `RESTIC_REST_PASSWORD`, and `RESTIC_PASSWORD`.

Schedules:

- Backup: daily `0 3 * * *`
- Maintenance: weekly `0 4 * * 1`
- Retention: daily 14, weekly 8, monthly 12, yearly 3
- Maintenance scope: `forget --group-by host,paths,tags --prune`, then
  `check`, then `check --read-data-subset=10%`

Expected snapshot families:

```text
homelab         /data/appdata                    appdata
edgards-mini    /Users/edgard/Documents          documents
edgard-desktop  C:\Users\Edgard\Documents        documents
```

## Restore Rules

- Restores are Ansible-driven through `task restic:restore` and
  `task restic:restore-all`.
- Plan-only mode is the default. Destructive work requires
  `confirm_restore=true`.
- `snapshot` defaults to `latest`.
- For `latest`, restore selection is constrained to the Kubernetes appdata
  snapshot family: host `homelab`, tag `appdata`, path `/data/appdata`.
- Restore execution creates a temporary `restic-restore` Job, pauses generated
  app updates, disables automated sync for target apps, scales workloads down,
  deletes the existing target path contents, restores with
  `--exclude-xattr '*'`, scales workloads back up, restores sync policy, and
  deletes the restore Job.
- Restore-all includes Argo-managed `nfs-fast` appdata PVCs by default and
  excludes shared/static storage such as `media`, `restic-repo`, and
  `restic-appdata`.
- If a confirmed restore fails, leave apps paused/down until the restored data is
  inspected. Do not manually resume apps just to clear the failure.

## Restore One App

Preview first:

```sh
task restic:restore app=paperless
```

Run the restore with the latest Kubernetes appdata snapshot:

```sh
task restic:restore app=paperless confirm_restore=true
```

Run the restore from an explicit snapshot:

```sh
task restic:restore app=paperless snapshot=<snapshot-id> confirm_restore=true
```

The plan output shows the app, namespace, restic source paths, restore target
paths, and workloads that will be stopped and resumed.

## Restore One PVC

Restore the Argo CD app that owns the PVC. The role infers the app's restorable
PVCs from live Argo CD resources and live PVCs, so a single-PVC app is just a
single-app restore.

Example for Home Assistant:

```sh
task restic:restore app=homeassistant
task restic:restore app=homeassistant confirm_restore=true
```

Expected inferred path:

```text
/data/appdata/home-automation/homeassistant
```

## Restore All Appdata

Preview the full restore set:

```sh
task restic:restore-all
```

Run the full restore:

```sh
task restic:restore-all confirm_restore=true
```

Run the full restore from an explicit snapshot:

```sh
task restic:restore-all snapshot=<snapshot-id> confirm_restore=true
```

Use restore-all for full cluster appdata recovery. The role prepares all planned
apps first, restores all planned data, then resumes apps after the data phase
completes.

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

The Ansible role keeps the important manual restore flags in one place. If a
manual restore is ever needed for debugging, keep these constraints:

- Restore into `/restore`.
- Include only paths under `/data/appdata/<namespace>/<pvc-name>`.
- Delete only contents under `/restore/data/appdata/<namespace>/<pvc-name>`.
- Use `--exclude-xattr '*'` for NFS-backed appdata.
- Filter `latest` with `--host homelab --tag appdata --path /data/appdata`.
