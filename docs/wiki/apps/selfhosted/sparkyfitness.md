# SparkyFitness

Purpose: private fitness and nutrition tracking at sparkyfitness.edgard.org.
Status: current. Reviewed against: `881e92396dbd45e874ac2a68a0563e5784ca9faa`.

## Dependencies and startup

One Argo CD Application owns the packaged frontend/Nginx, backend, Garmin
microservice, dedicated PostgreSQL server and SQL-backup CronJob. The backend
runs its native database initialization at startup. This database serves only
SparkyFitness; no other application's database is migrated or shared.

The official PostgreSQL entrypoint initializes its volume and drops privileges.
The frontend uses its packaged Nginx template and a non-root listening port;
its upstream is the fully qualified backend service. Native backup/restore
routes remain available to the private administrator.

ESO supplies independent owner/runtime passwords and persistent API/auth
cryptographic keys. Private administrator creation uses the native auth API;
public registration stays disabled. Garmin authorization is completed
interactively in the application. AI, SMTP and other optional integrations are
not enabled by these values.

## Storage and backup

Uploads, backups and PostgreSQL use separate NFS claims. PostgreSQL18 stores its
versioned PGDATA below /var/lib/postgresql. The backend and backup CronJob share
the backup claim and volume group; SQL dumps occupy its postgresql subdirectory.
The backend inherits the default pod security context, including its NFS
`fsGroup`; a controller override replaces that context rather than merging it.

The app-local CronJob uses the matching official PostgreSQL image, publishes a
custom-format dump by rename only after success, and retains seven dumps.
Restic captures uploads and backup files while excluding live PostgreSQL data.
These are separate database/file capture times, not point-in-time or atomic
cross-resource recovery. Retain both API-encryption and auth-signing keys so
stored credentials remain usable after recovery.

## Restore

Establish the [SQL-app reconciliation holds](../../operations/restic-backup-restore.md#restore-all-appdata),
suspend the backup CronJob and wait for active backup Jobs to finish. Stop
frontend, backend and Garmin.
Preview `task restic:restore app=sparkyfitness`, choose the intended snapshot and
confirm its application-only scope. Keep application processes at zero while
files restore. The excluded PostgreSQL directory initializes fresh storage.
With PostgreSQL ready, use the backup workload's image, Secret and backup claim:

```sh
pg_restore --exit-on-error --clean --if-exists --no-owner --no-acl --dbname=sparkyfitness_db /backups/postgresql/<timestamp>.dump
```

Validate the database, uploads and retained keys, then resume backend, Garmin,
frontend, the prior backup CronJob suspension and reconciliation settings.
Native backend initialization recreates its runtime
role as needed. The [Restic runbook](../../operations/restic-backup-restore.md)
owns file-restore confirmation and scope rules.

## Networking and monitoring

Only the frontend has a route through the existing HTTPS Gateway. Backend,
Garmin and PostgreSQL services are internal. Gatus checks the public route;
Kubernetes probes cover component readiness. Garmin has HTTP startup and TCP
readiness, with no runtime liveness restart: legitimate synchronous upstream
work can block its HTTP event loop. TCP readiness is not proof of API progress.

## Sources

- [App metadata](../../../../apps/selfhosted/sparkyfitness/app.yaml)
- [Helm values](../../../../apps/selfhosted/sparkyfitness/values.yaml)
- [ESO credentials](../../../../apps/selfhosted/sparkyfitness/manifests/sparkyfitness-credentials.externalsecret.yaml)
- [Restic exclusions](../../../../apps/selfhosted/restic/values.yaml)
- [Upstream deployment](https://github.com/CodeWithCJ/SparkyFitness/blob/v1.11.0/docker/docker-compose.prod.yml)

## Related pages

- [Backup and recovery](../../architecture/backup-recovery.md)
- [Secrets](../../architecture/secrets.md)
- [Uptime monitoring](../../architecture/uptime.md)
