# PostgreSQL

Purpose: provide the shared PostgreSQL service for explicitly onboarded consumers.
Status: current. Reviewed against: `0f2fb9820f152e526c77dc6dfc16a17d040a5a8f`.

## Dependencies

The service depends on External Secrets and the retained NFS appdata class.
The administrator credential is delivered separately from application logins.
Application databases and restricted roles are provisioned through the
[shared-data operations](../../operations/shared-data.md) workflow. A Ready
database does not establish that application provisioning has completed.

## Data and recovery

The claim mounts the PostgreSQL parent directory; the major-version-specific
PGDATA path is owned by UID/GID 999. A narrow root init creates fresh directories
and checks ownership, without recursively changing an existing cluster. NAS
parents can pass setgid to a fresh directory. The init normalizes only an empty,
correctly owned bootstrap directory; nonempty data with unexpected permissions
remains rejected for inspection. Linked PGDATA paths are rejected before any
permission changes.
The server runs as UID 999 with a read-only root filesystem and separate
runtime/shared-memory mounts. The NAS must honor numeric ownership and stable
writes. PVC requests are not NFS quotas or reservations.

The connection ceiling and memory settings are owned by the values. Explicit
per-role budgets in the consumer registry leave administrator capacity.
Sparky's owner budget includes its separate owner and authentication pools;
its runtime role has a separate budget.

Live database files are excluded from ordinary Restic file capture and generic
destructive restores. Database-aware dump/recovery acceptance is required before
consumer activation. Major upgrades require compatibility and recovery
rehearsals; retained storage alone is not a backup.

## Networking and monitoring

The ClusterIP service provides the registry's internal database endpoint.
There is no public HTTP route. Authenticated SQL probes validate server
readiness; Gatus also checks TCP reachability. This keeps the existing trusted
Flannel network model and makes no NetworkPolicy isolation claim.

## Sources

- [App metadata](../../../../apps/platform-system/postgresql/app.yaml)
- [Values and startup checks](../../../../apps/platform-system/postgresql/values.yaml)
- [Storage and credentials](../../../../apps/platform-system/postgresql/manifests)
- [Consumer registry](../../../../ansible/roles/shared_data/files/registry.yaml)
- [Native startup/restart verification](../../../../tests/integration/test_shared_services.py)

## Related pages

- [Shared operations](../../operations/shared-data.md)
- [Storage](../../architecture/storage.md)
- [Backup and recovery](../../architecture/backup-recovery.md)

