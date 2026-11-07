# Sure

Purpose: private personal-finance tracking at sure.edgard.org.
Status: current. Reviewed against: `8b3bfc0792a0532ee6d27bea1802d0642db102ae`.

## Dependencies and startup

One Argo CD Application owns the web process, Sidekiq worker, dedicated PostgreSQL
and Redis servers, and database-backup CronJob. These engines serve only Sure;
other applications retain their existing databases. The native web entrypoint
runs Rails database preparation; a worker init container waits for web readiness.
The official PostgreSQL entrypoint starts as root for volume initialization and
then drops to its postgres user. Container privilege escalation stays disabled
and only its initialization capabilities are granted.

Independent database/Redis passwords, administrator credentials and stable Rails
encryption keys come from the namespace-local ESO Secret. Keep these Bitwarden
items during recovery. Private administrator onboarding closes public signup.
Optional AI, bank and SMTP integrations are not configured by these values.

## Storage and backup

The app owns separate NFS claims for shared Rails storage, PostgreSQL data, Redis
persistence and SQL dumps. Web and worker share the Rails-storage claim. Redis
uses authenticated AOF persistence and no eviction; it remains a queue/cache,
not the authoritative financial database.

The app-local backup CronJob uses the same official PostgreSQL image as its
server. It writes a custom-format dump to a temporary file, publishes it by
rename only after pg_dump succeeds, and retains seven published dumps. Its
schedule precedes nightly Restic. Restic includes Rails storage and SQL dumps;
live PostgreSQL and Redis directories are excluded. Database and file captures
are separate snapshots in time; this setup does not provide point-in-time or
transactionally atomic database-plus-file recovery.

## Restore

Establish the [SQL-app reconciliation holds](../../operations/restic-backup-restore.md#restore-all-appdata),
suspend the backup CronJob and wait for active backup Jobs to finish. Stop Sure
web and worker before restoring. Preview the existing `task restic:restore app=sure` operation, select
the intended snapshot, and confirm only Sure's claims. Keep web and worker at
zero throughout the file restore. PostgreSQL and Redis initialize fresh storage
because their live directories are excluded from backup.

With PostgreSQL ready, use the backup workload's image, connection Secret and
backup claim to run:

```sh
pg_restore --exit-on-error --clean --if-exists --no-owner --no-acl --dbname=sure /backups/<timestamp>.dump
```

Validate the selected database and Rails storage, then resume web, worker,
the prior backup CronJob suspension and reconciliation settings. Redis queues
are recreated; pending work may need retry. Retain
the same Rails encryption keys so stored credentials remain readable. The
[Restic runbook](../../operations/restic-backup-restore.md) owns the file-restore
confirmation and scope rules.

## Networking and monitoring

Only the web service has an HTTPS route through the existing Gateway. PostgreSQL
and Redis are ClusterIP services. Gatus checks the routed /up endpoint; normal
startup and readiness probes cover application and engine startup.

## Sources

- [App metadata](../../../../apps/selfhosted/sure/app.yaml)
- [Helm values](../../../../apps/selfhosted/sure/values.yaml)
- [ESO credentials](../../../../apps/selfhosted/sure/manifests/sure-credentials.externalsecret.yaml)
- [Restic exclusions](../../../../apps/selfhosted/restic/values.yaml)
- [Upstream deployment](https://github.com/we-promise/sure/blob/v0.7.6/compose.example.yml)

## Related pages

- [Backup and recovery](../../architecture/backup-recovery.md)
- [Secrets](../../architecture/secrets.md)
- [Uptime monitoring](../../architecture/uptime.md)
