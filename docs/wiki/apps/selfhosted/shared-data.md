# Shared data operations

Purpose: supply storage, credentials, and Kubernetes permissions for coordinated data maintenance.
Status: current. Reviewed against: `1b080d18e9d8e06deef71c2b8b37afda73d92c3c`.

## Dependencies

The app uses External Secrets, retained staging storage, the existing Restic
appdata/repository services, and a published digest-pinned operations image.
Its registry ConfigMap mirrors the role-owned registry; configuration tests
require identical content. Registry removal never deletes databases or roles.

## Rollout gate

Backup, provisioning, and watchdog CronJobs are initially suspended. This
infrastructure stage prepares their Pod templates and permissions; activation
requires the subsequent tested orchestration image and recovery acceptance.
The backup heartbeat is disabled during this phase. Consumer adoption flags
remain false, and prepared namespace-local Secrets do not change active
application connection settings.

## Data and recovery

Staging is retained and excluded from generic Restic capture/restoration.
The operations Pod mounts the canonical appdata path for controlled capture
and selected-app recovery. The watchdog template has no PVC or NFS mount.
The maintenance Lease and original-state journal live in Kubernetes, so
storage failure does not hide the recovery record.

## Permissions and monitoring

Cluster RBAC is read-only for Pods, Jobs, Nodes, and upgrade resources.
Namespace Roles grant the required named workload/Application mutations and
operation-object management. Named Application grants include PostgreSQL and
Redis so their independent reconciliation can be held without stopping engine
servers or exposing raw database volumes. They do not list Secrets. The selfhosted
AppProject explicitly permits these Roles in the affected namespaces; this
also expands that GitOps project's permitted destination namespaces.

Bounded standalone operator Pods support a held transition across a source
merge. Their scoped exec and Service/EndpointSlice permissions implement the
[Paperless enrollment procedure](../../operations/paperless-enrollment.md).
They use frozen image-owned logic and temporary storage without application
data or database credentials. Actor UID, desired source and rendered template
checks prevent adopting a replacement actor or resuming an incompatible Pod.

Gatus has shared-service TCP checks and separate external endpoints for
operation health and verified capture freshness. The watchdog receives only its
heartbeat token, without database credentials or application storage. Freshness
advances only after a verified full-scope upload and uses capture time, so a
successful provisioning job or delayed older upload cannot reset it. Endpoint
activation accompanies the accepted backup path.
See the [operations procedure](../../operations/shared-data.md) for transaction
ownership, failure holds, and staged delivery.

## Sources

- [App metadata](../../../../apps/selfhosted/shared-data/app.yaml)
- [Paused schedulers and mounts](../../../../apps/selfhosted/shared-data/values.yaml)
- [Registry, RBAC, credentials, and staging](../../../../apps/selfhosted/shared-data/manifests)
- [AppProject destinations](../../../../argocd/projects/selfhosted.appproject.yaml)
- [Infrastructure safety checks](../../../../tests/config/kubernetes/test_shared_data.py)
- [Gatus configuration](../../../../apps/platform-system/gatus/values.yaml)

## Related pages

- [Shared-data operations](../../operations/shared-data.md)
- [PostgreSQL](../platform-system/postgresql.md)
- [Redis](../platform-system/redis.md)
- [GitOps delivery](../../architecture/gitops-delivery.md)

