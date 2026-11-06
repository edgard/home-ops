---
# Kubernetes Restic Restore Runbook

Purpose: operator procedure for a Kubernetes appdata restore.
Status: current. Reviewed against: `20ab0bc1d62963bbe4abcb439ec491e2e9074403`.

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
before relying on a schedule. Kubernetes owns repository-wide retention and
pruning, including workstation snapshots; clients only create backups. Retention
groups snapshots by host, paths, and tags and explicitly keeps all
`appdata-pending` snapshots for the separate inspected cleanup command.

## Rules

The Task entry points use the shared-data coordinator for database and file
recovery. Activation requires its published, digest-pinned orchestration image;
operation schedulers remain paused until recovery acceptance.

- Preview first. Existing commands retain `confirm_restore=true`; the new
  `data:restore` commands use `confirm=true`. Check mode always previews.
- `latest` selects a canonical `appdata` snapshot for host `homelab` covering
  every selected consumer. Pending uploads and workstation snapshots are excluded.
- Restore-all includes registered consumers; review the printed registry scope.
  Shared media, repository storage, live PostgreSQL, Redis persistence, and
  staging claims are excluded from destructive file restoration.
- PostgreSQL consumers require complete database manifests and compatible images
  and encryption keys. Historical manifest-less snapshots are eligible only for
  consumers still on file/SQLite backends.
- The coordinator holds root reconciliation first, then ApplicationSet and child
  updates, schedules, and registered writers. It stages and validates data,
  restores only the selected databases and files, verifies writes, and resumes
  recorded settings with root last. A temporary authenticated Redis source
  restores only selected adopted allocations and preserves absolute expirations.
- Destructive failure remains held. Inspect the journal and data before explicit
  recovery or resumption; clearing a failed Job does not establish consistency.

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

The plan shows each consumer's backend, databases, Redis allocation, PVCs,
and workloads. Restore the registered application that owns the data.

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

Rebuild Talos/Kubernetes and reattach the repository and application storage.
Recover External Secrets and the required encryption keys, then recovery tooling,
Restic, PostgreSQL, and Redis. Keep root reconciliation, consumer Applications,
consumer workloads, and operation schedules held while restoring. Do not allow
ordinary bootstrap reconciliation to start consumers against empty databases.

Preview `task restic:restore-all`, review snapshot compatibility and scope, then
restore with confirmation. Validate databases, files, authentication, and queues
before enabling consumers and resuming root last. Existing zero-replica and
held-policy settings remain held after restore. Automated cold infrastructure
bootstrap is a separate acceptance gate before PostgreSQL consumer activation.
Run a fresh backup after recovery.

## CLI fallback

Use the role for normal recovery. A manual Restic file extraction cannot restore
a PostgreSQL-era application consistently. For inspection, extract into a private
staging directory, select explicit canonical snapshot identities and registered
paths, and preserve the source snapshot. Never restore raw PostgreSQL or Redis
persistence over shared live services.

## Sources

- [Restic deployment](../../../apps/selfhosted/restic/values.yaml)
- [Restore task entry points](../../../Taskfile.yaml)
- [Database-aware restore role](../../../ansible/roles/shared_data/tasks/restore.yml)
- [Compatible restore entry point](../../../ansible/playbooks/restic-restore.yml)
- [Registry restore planning](../../../ansible/roles/shared_data/tasks/plan.yml)
- [Restore automation PR](https://github.com/edgard/home-ops/pull/261)

## Related pages

- [Backup and recovery architecture](../architecture/backup-recovery.md)
- [Storage](../architecture/storage.md)
