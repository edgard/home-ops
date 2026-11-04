# Shared data services and application rollout

Approved implementation contract, 2026-11-04. The user requested continued execution through verification and cleanup.

## Global constraints

- All repository changes through staged PRs on `codex-` branches; never commit to master.
- Existing app-template 5.3.0 pattern, single replica, Recreate, retained nfs-fast storage.
- PostgreSQL 18: internal postgresql.platform-system.svc.cluster.local:5432, 50Gi, 1Gi request/4Gi limit, 200 connections, 256MB shared_buffers, 4MB work_mem. PVC at /var/lib/postgresql; PGDATA=/var/lib/postgresql/18/docker.
- Redis 8.10.3: internal redis.platform-system.svc.cluster.local:6379, 5Gi, 128Mi request/1Gi limit, AOF everysec, maxmemory 256mb, noeviction. Keep Argo Redis independent.
- Registry drives per-app databases, independent credentials, Redis DB allocations, writer inventory, PVCs and recovery. Never delete data automatically on registry removal.
- Bitwarden/ESO secrets, add home-automation to allowed namespaces, no plaintext secrets or app superuser/CREATEDB/CREATEROLE/BYPASSRLS. Precreate Sparky owner/runtime roles; Sure pgcrypto only in Sure DB.
- Preserve current Flannel trust model; no claimed NetworkPolicy isolation.
- Sure v0.7.6 web+worker, sure.edgard.org, 5Gi storage; 512Mi request each. SparkyFitness v1.11.0 frontend/backend/Garmin, sparkyfitness.edgard.org, 5Gi uploads+2Gi backups; requests 64/256/128Mi. Pin published image digests. Persist encryption/auth keys. Block native Sparky restore at /api/admin/backup/restore (normalized, case-insensitive). Initial private onboarding/Garmin authorization; optional AI/SMTP/bank integrations off.
- Paperless same-version native data-only migration, preserve GPT files/index/settings and API-token identity. Bambuddy native portable backup/restore. Atuin typed transfer preserving IDs/users/sessions/encrypted records, exclude backend migration ledgers. Servarr main+log data-only rehearsals preserving data; Bazarr timestamp casts. HA fresh PostgreSQL recorder; archive SQLite history/statistics. No unrelated app upgrades.
- Shared maintenance Lease and Kubernetes ConfigMap journal BEFORE mutations; fence root, appset, affected app sync and in-flight syncs; suspend all registered Jobs/CronJobs/producers, drain tasks, stop writers, verify no DB sessions. Hold node upgrades/conflicting operations. Fence migration consumers before merging configuration changes. Restore exact state, root last.
- Daily03:00 Europe/Warsaw+prechange backups. Preseed files online then final delta+PG18 custom dumps+Redis RDB while quiescent.180s healthy-platform pause budget, not outage guarantee.200Gi staging, two generations+20% free-space preflight. Immutable manifests with backend/images/schema/key refs/checksums. New upload Pod per published generation preserves /data/appdata/ns/PVC paths. Exclude raw PGDATA/AOF/staging. appdata-pending until successful verified upload; failed snapshots must not become latest.
- Watchdog WITHOUT NFS reads API journal, fences coordinator/childJobs before recovery. Failed destructive restores stay held. Restore selected app SQL/files/Redis DB only, preserved queues/expiries. Reject missing/incompatible manifests; retain encryption-key versions. Exclude infrastructure PVCs from generic restore. Cold recovery bootstraps infrastructure only, then restore, then consumers.
- Operations container built/published and digest-pinned before deployments reference it. Role-owned Ansible orchestration, kubernetes.core for API operations, native CLI adapters for data operations. Reuse same local/scheduled logic. Gatus health/freshness, full contract/integration/recovery tests and task check. First substantive November PR performs semantic wiki review.

## Tasks

### Task 1: Operations and maintenance foundation

Create registry validation, reversible maintenance and fencing, operations image/build workflow, role playbooks/Task interfaces, tests and operational documentation. Independently verify recovery after interruption and precise state restoration. Publish image through its PR before deployment manifests use it.

### Task 2: Shared services and recoverable backups

Add singleton PostgreSQL/Redis, ESO credential wiring, explicit idempotent provision Job, backup generation/capture/upload/promotion, watchdog/status, selected-app/full restore and cold-bootstrap mode. Verify fresh provisioning/permissions and isolated recovery on disposable data first.

### Task 3: New applications

Add Sure and SparkyFitness resources, migration/readiness gates, secret references, storage and Gatus checks. Verify with disposable services before live deployment and private onboarding.

### Task 4: Existing application migrations

Implement native/typed adapters, rehearsal evidence and guarded cutover transactions. Stage Paperless, Bambuddy, Atuin, each media app, then fresh HA recorder. Fail closed on failed rehearsal; preserve originals and accepted identity/data invariants.

### Task 5: Review, rollout and cleanup

Review the full branch, run required repository checks and actual runtime/recovery checks. Stage PRs and satisfy credential/NAS prerequisites before deployment. Remove disposable data/jobs, restore policies, verify live consumers and backups, retain rollback archives until acceptance. Record actual completed vs blocked work honestly.
