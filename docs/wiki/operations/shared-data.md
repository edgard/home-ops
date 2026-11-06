# Shared application data operations

Purpose: explain the shared-data operations foundation and rollout prerequisites.
Status: current. Reviewed against: `20ab0bc1d62963bbe4abcb439ec491e2e9074403`.

## Delivery stage

The [rollout plan](../../superpowers/plans/2026-11-04-shared-data-services.md)
introduces shared PostgreSQL and Redis, then new applications and individually
rehearsed migrations. The first stage supplies a role-owned maintenance
coordinator, native data adapters, an operations image, and isolated tests.
Consumer cutovers and the remaining orchestration follow in later PRs. The
[registry](../../../ansible/roles/shared_data/files/registry.yaml) records intended
database ownership, connection budgets, Redis allocations, writers, file paths,
and encryption-key references. Its adoption flags remain false until each
application passes its cutover gate. Removing a registry entry does not run SQL
or delete databases, roles, or persistent files.

The [PostgreSQL](../apps/platform-system/postgresql.md),
[Redis](../apps/platform-system/redis.md), and
[operations infrastructure](../apps/selfhosted/shared-data.md) definitions now
prepare the shared services and storage. All operation schedulers remain paused
until backup/recovery orchestration is wired and accepted. Prepared consumer
Secrets do not activate application migrations. The existing daily file backup
continues for unchanged applications and excludes live database and staging
directories.

The [Restic runbook](restic-backup-restore.md) enters the database-aware
coordinator through both existing and new Task commands. The source-owned
operations image must be published and pinned before these commands or paused
schedulers are activated. Shared PostgreSQL consumers require database-aware
backup and recovery before activation; a file snapshot of a PostgreSQL data
directory is not the recovery contract.

## Maintenance coordination

The [Ansible role](../../../ansible/roles/shared_data/tasks/maintenance.yml)
uses a Kubernetes Lease for exclusivity and a ConfigMap journal for original
resource identities and settings. These live in the Kubernetes API rather than
on NFS. Operations require explicit confirmation, a registered scope, and a
live coordinator Pod UID. Plan and Ansible check mode do not mutate resources.

The coordinator holds root reconciliation before ApplicationSet and child
Application updates, waits for active syncs, suspends registered schedules,
checks node-upgrade work, and stops writers. Queue consumers need registered
drain checks and termination grace sufficient for active work. Original
fields, including absent fields and replica counts, are restored with root
resumed last. Resource replacement or conflicting ownership fails closed.

For enrolled Sure and Paperless Pods, the registry supplies native producer
pause, worker quiet, idle checks, and recovery commands. The coordinator records
pause intent and Pod identity before executing them. Queued broker work remains
pending; active, reserved, and in-memory scheduled work must finish. Recovery
restarts a quiet Sidekiq worker only after idle, while Paperless can restore
native consumption and producer services on its original Pod. Missing replies
or uncertain termination keep reconciliation held.

Preflight checks the actual Pod's grace, image, and relevant settings. Updating
a Deployment template does not extend an existing Pod's shutdown grace.
Paperless's old-Pod enrollment needs a separately tested transition before its
new grace/probe template or database cutover is applied; the normal capture
protocol refuses an incompatible Pod. A prepare-only hold records that writers
remain untouched. If resumption then fails, recovery preserves that boundary;
transactions that touched writers retain the stricter fail-closed behavior.

Automatic recovery is restricted to interrupted backups after the old
coordinator and its child work have been fenced. Restore, migration, and
rotation failures remain held for inspection. An independent watchdog uses
the API journal and does not require an NFS mount. API, storage, or node
failure can prevent recovery; the pause target does not guarantee downtime.

## Native adapters and recovery boundaries

The [data adapter](../../../ansible/roles/shared_data/files/data_tools.py)
creates restricted PostgreSQL application roles and database grants, produces
custom-format dumps, and restores only selected databases. Credentials are
read from mounted files. Application connection budgets leave administrator
capacity below the server ceiling. Provisioning reruns do not silently rotate
passwords. Cluster-wide application privileges are rejected.

Redis users have separate passwords, logical databases, and Pub/Sub channel
prefixes. Logical databases share one trust and failure boundary: Redis ACLs
do not restrict which logical database a user can select. The adapter blocks
global administrative and destructive commands; real application queue,
cache, and Pub/Sub acceptance remains a rollout requirement. A selected Redis
database can be recovered from a temporary isolated source while preserving
absolute key expirations and other allocations.

The [capture helper](../../../ansible/roles/shared_data/files/capture.py)
pre-copies selected files while writers remain online, then finalizes a
stopped-writer generation with content checksums and durable rename publication.
The normal pause budget begins before producers are paused, includes draining,
and is never restarted after writers stop. Expiry aborts capture; safely
finishing active application work can require a longer pause. The
[upload helper](../../../ansible/roles/shared_data/files/upload.py)
creates pending Restic snapshots and promotes only a successful, verified
generation. Exit code 3 remains pending. Raw PostgreSQL files, Redis persistence,
and staging files are excluded. Deployment wiring must mount the exact
published generation in a newly created upload Pod at the canonical paths.

Provisioning new credentials needs an authorized Bitwarden write path.
The ESO/SecretSpec machine account normally has read-only access. If an operator
temporarily grants it write access for provisioning, restore read-only access
after delivery and authentication are verified. Keep values in Bitwarden and
deliver namespace-local Secrets through ESO.

## Operator commands and monitoring

`task data:backup`, `data:provision app=<name>`, `data:restore app=<name>`,
`data:restore-all`, `data:cleanup`, and `data:watchdog` preview their scope without contacting
the cluster. Set `confirm=true` only after reviewing the plan. Confirmed
commands submit bounded Jobs using the same role as scheduled operations.
The captured registry must still match the live registry before data Jobs
acquire maintenance ownership; delayed Jobs cannot apply obsolete mappings.

Native backup and provisioning accept only entries in `registry.consumers`,
including existing SQLite consumers before onboarding. File-only entries in
`registry.file_consumers`, whether selected alone or alongside native consumers,
are rejected before preview, Job submission, or maintenance coordination. Restore
and cleanup continue to accept combined native and file scopes. Direct backup
and provisioning task entry points enforce the same guard before cluster access.

`data:cleanup confirm=true` separately forgets unpromoted pending snapshots
older than seven days. It holds reconciliation and schedules, verifies upload
actors are finished, and leaves application writers online. Canonical snapshots,
including ambiguous snapshots carrying both tags, are never eligible. Normal
repository retention applies across all host/path/tag groups, including workstation
snapshots, and explicitly keeps every `appdata-pending` snapshot for this separate
cleanup. Repository pruning later reclaims unreferenced data.

Restore stages and validates the selected snapshot before replacing data.
The API journal binds snapshot identity, exact manifest bytes, and selected
scope. PostgreSQL-era recovery requires database manifests, compatible images,
and retained encryption keys. Historical manifest-less snapshots are accepted
only for consumers still using their file or SQLite backend. A selected Redis
allocation is recovered through an authenticated, isolated temporary Redis
source, leaving other allocations unchanged. Failures after destructive work
remain held for inspection.

Gatus operation health and backup freshness have separate external endpoints.
The API-only watchdog reports stale ownership and failed coordinator/upload
Jobs. Backup freshness uses the capture time of the last verified full-scope
upload, rather than upload completion or provisioning time; delayed retries
cannot overwrite a newer capture record. Its heartbeat credential is mounted
only in the watchdog, without database credentials or NFS. Endpoints remain
disabled until rollout acceptance. These checks cannot provide an external
alert during a complete single-node or monitoring outage.

## Image and verification

The [image workflow](../../../.github/workflows/data-tools.yml) builds on PRs
and publishes commit-tagged images from master. Consumers must use the
published digest. The image contains PostgreSQL-major-matched clients, Redis
tools, Restic, and the role-owned adapters. It carries no operator secrets.

Unit and synthetic Kubernetes API scenarios verify input guards, original
state, concurrency and interruption behavior. Disposable PostgreSQL and Redis
tests verify role restrictions, custom dump recovery, types and sequences,
ACLs, and selected database recovery. Native Restic tests use a disposable
local repository. These checks supplement fresh-install, migration rehearsal,
single-app restore, cold-recovery, and failure acceptance in the rollout plan.

## Sources

- [Role defaults and entry point](../../../ansible/roles/shared_data)
- [Operations playbook](../../../ansible/playbooks/shared-data.yml)
- [Image build](../../../containers/data-tools/Dockerfile)
- [Maintenance integration scenarios](../../../tests/integration/test_data_maintenance.py)
- [Native database scenarios](../../../tests/integration/test_data_native.py)
- [Native Restic scenario](../../../tests/integration/test_data_restic.py)

## Related pages

- [Backup and recovery](../architecture/backup-recovery.md)
- [Restic procedure](restic-backup-restore.md)
- [Secrets maintenance](secrets-maintenance.md)
- [GitOps delivery](../architecture/gitops-delivery.md)
