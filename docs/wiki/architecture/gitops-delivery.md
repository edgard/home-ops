# GitOps delivery

Purpose: explain how a repository change becomes a cluster application.
Status: current. Reviewed against: `e0ffdb032870a9272c7abd691788e9b4e4b48ee1`.

Ansible installs foundational services and the Argo CD controller. The separate
handoff applies the root Application, which installs namespaces, projects, and
the `apps` ApplicationSet. That ApplicationSet reads each `apps/*/*/app.yaml`
on `master`, combines its chart with the matching values file and optional raw
manifests, and reconciles the generated Application. Sync waves order
prerequisites before apps. Changes reach the cluster through a merged PR.

## First installation and recovery

Run `task platform:foundation` against the verified Talos node. It checks the
pool's four enrolled members, the actual shared filesystems and media root
permissions, then records the boot disk and pool GUID in the immutable
`kube-system/storage-identity` ConfigMap before starting the CSI driver. The
existing encrypted Restic repository, its authentication file and matching
Bitwarden credentials are prerequisites. The foundation exposes the repository
read-only inside the cluster while application writers are held.

With no GitOps owners or application storage consumers, `task platform:claims`
creates the app-owned PVCs rendered from the current charts. Temporary
read-only Pods trigger OpenEBS first-consumer binding. The platform and restore
tasks share an exclusive Kubernetes lock while preparing, restoring or releasing
these volumes.

- **Rebuild from backups.** Restore each claim and verify its contents. Recover
  and check the native PostgreSQL database and uploads for SparkyFitness.
  The Restic recovery task creates a held checkpoint and records its identity
  for each verified file restore automatically. Supply `PLATFORM_RECOVERY_FILE`
  for the native database and any manually recovered datasets. Handoff matches
  every receipt to its live PVC,
  retained PV, OpenEBS record, filesystem and snapshot GUID and checks for
  changes since verification. The [recovery runbook](../operations/restic-backup-restore.md)
  describes the per-claim procedure.
- **First-ever empty installation.** Set `PLATFORM_NEW_APPDATA=true` instead.
  Each prepared claim must be empty on its actual filesystem. The CSI parent
  must contain exactly these new datasets with no snapshots, and the verified
  repository must have no previous homelab appdata backups.

Use `PLATFORM_HANDOFF_CONFIRM=true task platform:handoff` after completing the
appropriate path. It verifies the static media and repository PVs, current
OpenEBS bindings and repository identity before releasing GitOps. A later
handoff recognizes the running root by its repository sources, project and
destination and checks the current storage owners. If an interrupted handoff
already created the root, rerun it with the same checkout.

Bootstrap preflight requires a clean checkout matching remote `master`.
Handoff verifies that the root synchronized the captured revision, generated
children belong to the expected ApplicationSet, and External Secrets refreshed.
The [agent workflow](../agent-workflow.md) covers changes and validation.

## Sources

- [Platform bootstrap](../../../ansible/roles/platform/tasks/bootstrap.yml)
- [Claim preparation](../../../ansible/roles/platform/tasks/create_claims.yml)
- [Storage handoff checks](../../../ansible/roles/platform/tasks/verify_storage.yml)
- [Root handoff](../../../ansible/roles/platform/tasks/release_root.yml)
- [Root Application](../../../argocd/root.app.yaml)
- [Apps ApplicationSet](../../../argocd/appsets/apps.appset.yaml)
- [Application discovery](../../../validation/sources.py)

## Related pages

- [Talos bootstrap](talos-bootstrap.md)
- [Validation](validation.md)
- [App catalog](../index.md#applications)
