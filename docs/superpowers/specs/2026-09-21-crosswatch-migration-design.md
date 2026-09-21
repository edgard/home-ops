# CrossWatch migration design

## Intent and success criteria

Replace the failed Trakt-dependent PlexTraktSync path with a self-hosted record of
watched movies and episodes. Keep Plex as the playback source, import the existing
Trakt export without a Trakt subscription, and make future Plex watches appear in
CrossWatch automatically. Use one container, one SQLite-backed PVC, and the
cluster's existing backup system. The user chose CrossWatch and accepts the
cluster's established NFSv4 pattern for SQLite.

The migration succeeds when the Trakt archive has been imported and reconciled,
new Plex watch events reach the local tracker, a full CrossWatch backup can be
validated and restored, and PlexTraktSync can be removed without losing its
rollback data. CrossWatch must remain available after a pod restart.

## Scope

- Deploy CrossWatch v0.12.3 in the `media` namespace using the pinned
  `ghcr.io/cenodude/crosswatch:0.12.3` image and the repository's app-template
  chart. Use one `Recreate` deployment and one `nfs-fast` PVC mounted at
  `/config` (initially 5 GiB). CrossWatch listens on port 8787 with
  `TZ=Europe/Warsaw`. The pod runs as UID/GID 1000 with privilege escalation
  disabled and all capabilities dropped.
- Connect CrossWatch to the existing Plex server at
  `http://plex.media.svc.cluster.local:32400` and to its built-in local tracker.
  A Watcher records future Plex watch events to that tracker. Start with the
  existing user's Plex account only, and set the watched threshold to 80%,
  matching PlexTraktSync's current policy. Do not enable reverse writes to Plex
  or recurring Trakt sync.
- Import `~/Downloads/trakt-export-edgard.zip` into the local tracker using
  CrossWatch's Trakt ZIP importer. Include history and ratings; the archive has
  no watchlist entries. Keep the original ZIP unchanged as a migration source.
- Add `https://crosswatch.edgard.org` through the existing HTTPS Gateway and a
  Blackbox HTTP probe after initial authentication has been configured.
- Retire the broken PlexTraktSync deployment, CronJob, app metadata, and secret
  only after import and new-event checks pass. Retain its PVC until rollback is
  no longer needed. Do not alter unrelated media applications.

The Trakt export's collection records are outside the requested watched-status
migration: CrossWatch's importer does not support Trakt `collection-*` files.
This design also excludes multiuser migration, bidirectional sync, Simkl sync,
and any Trakt API authorization.

## Architecture and data flow

```text
Plex playback/history ──Plex Watcher──> CrossWatch local tracker
                                           │
Trakt export ZIP ──one-time importer───────┘
                                           │
                                           ├── /config on media/crosswatch-config
                                           ├── full CrossWatch ZIP backup on /config
                                           └── daily Restic snapshot of appdata
```

The CrossWatch pod, local tracker, encrypted provider settings, SQLite
databases, and generated encryption key all live under `/config`. The container
needs no PostgreSQL, Redis, media library mount, or Multus address. The Plex
connection stays inside the cluster; only the authenticated web UI uses the
public Gateway hostname. CrossWatch's generated `.cw_master_key` stays on the
PVC and in encrypted Restic backups; it is never committed to Git.

The current cluster already runs SQLite applications on `nfs-fast`, so the
single-PVC layout follows a working local convention. SQLite's WAL documentation
does not support WAL over network filesystems, including NFS. This remains a
real durability risk despite the NFSv4 precedent. The deployment must keep one
pod, use `Recreate`, and maintain a tested, application-consistent full backup.
Do not claim NFSv4 makes SQLite WAL safe. If database lock, I/O, or corruption
errors appear, stop writers and move `/config` to node-local/block storage before
resuming; do not add replicas or retry destructive writes.

## Authentication and configuration

Deploy the service and PVC first without an external HTTPRoute. Reach the UI
temporarily through a local `kubectl port-forward`. During first-run setup, the
user chooses an admin password; no password is placed in Git or terminal output.
Confirm login succeeds and anonymous requests to protected API paths fail.
Only then add the route and Blackbox probe through a GitOps PR. Route exposure
is limited to the cluster's existing LAN/Tailscale gateway policy.

Use CrossWatch's Plex PIN authorization flow in the UI to connect the account,
then select the existing internal Plex server and the intended Plex user. This
requires one interactive sign-in from the user. Create or connect the local
tracker in CrossWatch. Configure a Plex-to-local Watcher with autostart and the
80% watched threshold. Verify the Watcher is running after a pod restart.
Configuration stored in `/config` must persist; no one-off manual launch
command may be required after restart.

## Trakt migration and reconciliation

The local source archive was validated on 2026-09-21: 759,193 compressed bytes,
5,781,049 uncompressed bytes, 87 ZIP members, and no CRC error. It contains
9,978 history rows (519 movie and 9,459 episode events), 35 rating rows, and no
watchlist rows. The latest watched event is dated 2026-06-02, matching the
latest Plex history date observed during discovery. Three Trakt history rows
are dated in 1970 and require explicit review in the import preview.

Take a pre-import full backup, upload the original ZIP through CrossWatch's
Trakt ZIP importer, and inspect the preview before committing. Commit history
and ratings to the local tracker. Record the import report: accepted, duplicate,
skipped, unmatched, and failed row counts with reasons. Reconcile every input
row to an imported event or a documented duplicate/skip. Sample movies,
episodes, repeat watches, ratings, and the three 1970 events in the UI or API.
If the importer rejects an expected record, correct the mapping or document a
specific limitation before considering the migration complete. Avoid a blind
second commit; use the report and a pre-import backup for recovery.

The ZIP is under CrossWatch's documented 25 MiB upload and 50,000-row limits.
The expected total is a reconciliation baseline, not a promise that 9,978
distinct watched titles will appear: history events may include rewatches or
duplicates.

## Backups and recovery

Configure CrossWatch's own scheduled backup with `scope: full` for 02:00
Europe/Warsaw, before the cluster Restic CronJob at 03:00. The default
`app_state` scope omits the local tracker and is insufficient. Store the full
ZIP under `/config/backups`, so the existing Restic appdata snapshot captures
both the application files and the validated backup artifact. Retain ten local
backup ZIPs at most, and check PVC usage after the first full backup. Expand
the claim before it reaches 80% usage; leave free space for SQLite and at least
one additional backup.

After import, create a full backup manually. Inspect its manifest for the
local tracker (`.cw_provider`), `config.json`, `.cw_master_key`, and SQLite
database snapshots; treat a fallback raw DB copy as a backup failure until
investigated. Validate the ZIP with CrossWatch's backup validation API and run
one disposable restore test before relying on it. Check that the next Restic
snapshot includes the CrossWatch PVC and the full ZIP. The restore procedure is
the existing `task restic:restore app=crosswatch` workflow, followed by a
CrossWatch login, local tracker history check, and Watcher check. A CrossWatch
full ZIP can be used to recover a damaged application state when the restored
PVC alone is insufficient.

## Rollout and cutover

1. Add the CrossWatch app without a public route. Validate rendered manifests,
   repository policies, and the deployment; sync it through Argo CD. Confirm
   PVC mount, pod readiness, service reachability, and application login flow.
2. Complete first-run admin setup via port-forward, then add the route and
   Blackbox probe through a separate GitOps change. Verify route access and
   that unauthenticated API requests remain protected.
3. Connect Plex and the local tracker; configure the Watcher. Capture a full
   pre-import backup, import the Trakt ZIP, and reconcile the report. Create and
   validate a full post-import backup; perform a disposable restore test.
4. Observe a real new Plex watch event flowing into the tracker. Confirm it is
   recorded once and survives a CrossWatch pod restart. If no natural event is
   available, use a disposable Plex library item and clean up only that test
   item after verification.
5. Confirm Argo CD `Synced` and `Healthy`, HTTP probe success, no CrossWatch or
   Plex database/auth errors in recent logs, and a successful Restic snapshot.
   Then remove PlexTraktSync's failing workload, CronJob, Argo app metadata,
   and ExternalSecret in a separate PR. Preserve its PVC and the Trakt ZIP.
   Verify old alerts clear without masking other failures.

Keep PlexTraktSync available until step 4 succeeds. It currently fails Trakt
OAuth with `invalid_grant`, so it is not an authoritative source for new data.
If CrossWatch fails before cutover, leave PlexTraktSync resources and restore
CrossWatch from the pre-import backup. If it fails after cutover, restore the
CrossWatch PVC/full ZIP and reconcile Plex events since the last good backup;
the original Trakt ZIP remains available for a fresh import. Never delete
CrossWatch data as part of rollback without verifying a usable backup.

## Acceptance evidence

- `task lint` and the repository's required PR checks pass on the exact head.
- Argo CD shows the new app `Synced` and `Healthy`; the pod is ready and the
  `/healthz` endpoint, authenticated UI, and Blackbox probe work. `/healthz`
  is a shallow process check, so UI and data checks are separate.
- The import report reconciles the ZIP history and ratings, with any skips
  explained; sampled watched events and ratings match the source.
- The Watcher records one new Plex watch, persists its state after restart,
  and has no relevant errors in logs.
- A full backup is validated, a disposable restore proves it usable, and a
  successful Restic snapshot contains the CrossWatch PVC and backup ZIP.
- After removal, no PlexTraktSync CronJob runs or related alerts remain, and
  unrelated media workloads are still healthy.

## References

- [CrossWatch v0.12.3](https://github.com/cenodude/CrossWatch/releases/tag/v0.12.3)
- [CrossWatch Trakt importer](https://github.com/cenodude/CrossWatch/blob/v0.12.3/services/importer.py)
- [CrossWatch backup implementation](https://github.com/cenodude/CrossWatch/blob/v0.12.3/services/backups.py)
- [CrossWatch Watcher guidance](https://wiki.crosswatch.app/crosswatch/settings/scrobbler/watcher)
- [SQLite WAL limitations](https://www.sqlite.org/wal.html)
- [Local Restic restore runbook](../../restic-backup-restore-runbook.md)
