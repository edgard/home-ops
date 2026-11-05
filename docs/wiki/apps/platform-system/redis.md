# Redis

Purpose: provide persistent shared Redis for explicitly registered queue/cache consumers.
Status: current. Reviewed against: `0f2fb9820f152e526c77dc6dfc16a17d040a5a8f`.

## Dependencies

The service uses the retained appdata class and an independent administrator
ExternalSecret. Argo CD's own Redis remains independent. Application users and
logical database allocations are provisioned separately from server startup.

## Data and recovery

The service uses AOF persistence, every-second synchronization, a bounded dataset,
and no eviction. These settings share one memory limit and failure boundary.
Future consumers must tolerate this queue-oriented policy.

A narrow root init prepares directory ownership, then UID 999 seeds the hashed
administrator ACL only when the ACL file is absent. An existing ACL is preserved
across restarts; empty or incorrectly owned ACL files fail startup. Changing the
ESO bootstrap password does not rotate a persisted ACL. Use a held, verified
credential rotation before changing clients.

The server runs as UID 999 with a read-only root filesystem. Raw AOF/data files
are excluded from ordinary file capture and generic destructive recovery.
Selected application recovery requires an isolated Redis source and must
preserve other logical database allocations and absolute expirations.

## Networking and monitoring

The ClusterIP endpoint is internal. Anonymous access is disabled, and readiness
requires authenticated PING. The native checks exercise the exact configured
probe commands for successful and failed authentication; TCP reachability alone
does not verify them. Gatus checks TCP reachability. Application users
have separate credentials and Pub/Sub prefixes, but logical databases are not
an ACL isolation boundary: a user can select another database. The cluster
remains trusted, without an asserted NetworkPolicy boundary.

## Sources

- [App metadata](../../../../apps/platform-system/redis/app.yaml)
- [Values, persistence policy, and probes](../../../../apps/platform-system/redis/values.yaml)
- [Storage and administrator credential](../../../../apps/platform-system/redis/manifests)
- [Native ACL/data adapters](../../../../ansible/roles/shared_data/files/data_tools.py)
- [Startup/restart verification](../../../../tests/integration/test_shared_services.py)

## Related pages

- [Shared operations](../../operations/shared-data.md)
- [Backup and recovery](../../architecture/backup-recovery.md)
- [Secrets maintenance](../../operations/secrets-maintenance.md)

