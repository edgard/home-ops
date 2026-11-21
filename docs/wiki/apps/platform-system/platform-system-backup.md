# Platform namespace backup

Purpose: protect the Grafana database and VictoriaMetrics history in the namespace Restic snapshot.
Status: current. Reviewed against: `ef58c5179dea280f1360556f6ba60166158840a7` and this revision.

The daily Job uses SQLite's online backup for Grafana and the VictoriaMetrics
snapshot API for metrics. These give each database a consistent recovery
point while it continues to serve traffic. The Restic container reads the
prepared images at the standard namespace claim paths. Data under `data/`
restores directly into each application's appdata PVC. Use the full snapshot
ID in the [restore runbook](../../operations/restic-backup-restore.md).

The backup uses the internal Restic service and a namespace-scoped secret.
After recovery, open Grafana, verify the shared uptime dashboard, and query
VictoriaMetrics at a timestamp preceding the backup.

## Sources

- [Application](../../../../apps/platform-system/platform-system-backup/app.yaml)
- [Backup job](../../../../apps/platform-system/platform-system-backup/values.yaml)

## Related pages

- [Backup and recovery](../../architecture/backup-recovery.md)
- [Restic runbook](../../operations/restic-backup-restore.md)
