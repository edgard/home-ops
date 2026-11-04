# Shared application data operations

Purpose: explain the shared-data operations foundation and rollout prerequisites.
Status: current. Reviewed against: `0eb60f6ccc54f3ad28e28fdebd0cf95ca27c1b16`.

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

The [existing Restic runbook](restic-backup-restore.md) remains the deployed
file-recovery procedure. Shared PostgreSQL consumers require database-aware
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
pre-copies selected files, finalizes a stopped-writer generation, checks
checksums, and publishes it by rename. The
[upload helper](../../../ansible/roles/shared_data/files/upload.py)
creates pending Restic snapshots and promotes only a successful, verified
generation. Exit code 3 remains pending. Raw PostgreSQL files, Redis persistence,
and staging files are excluded. Deployment wiring must mount the exact
published generation in a newly created upload Pod at the canonical paths.

Provisioning new credentials needs a separate authorized Bitwarden write path.
The shared ESO/SecretSpec machine account remains read-only. Keep new values in
Bitwarden, deliver namespace-local Secrets through ESO, and revoke temporary
writer access after provisioning and verification.

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
