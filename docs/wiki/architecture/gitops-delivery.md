# GitOps delivery

Purpose: explain how a repository change becomes a cluster application.
Status: current. Reviewed against: `d80872c8700249ef67aa42919e297c37e75faef3`.

Ansible installs foundational services and the Argo CD controller. After the
separate storage handoff, the operator releases the root Application. The
root application installs namespaces, projects, and the `apps` ApplicationSet.
That ApplicationSet reads each `apps/*/*/app.yaml` on `master`, combines its
chart with the matching values file and optional raw manifests, and reconciles
the generated Application. Sync waves order prerequisites before apps. A local
edit is not deployable until it is committed and pushed through a PR.

The per-app page records dependencies and operational context; the app metadata,
values, manifests, and generated Application remain the deployment definition.
The [agent workflow](../agent-workflow.md) gives the change and validation loop.

Bootstrap preflight requires a clean checkout matching remote `master`, then
verifies root reconciliation to that captured revision and expected ApplicationSet
children. ESO, repository credentials and the per-claim restore receipts must be
ready before handoff. The immutable handoff ConfigMap closes restoration before
the first application can start writing. With the root already running, a
repeat handoff validates the immutable record, live pool, permanent mounts and
current claim bindings before reconciling the merged revision. If the root is
absent, handoff repeats the original snapshot and content checks.

## Sources

- [Platform bootstrap](../../../ansible/roles/platform/tasks/bootstrap.yml)
- [Handoff authorization and evidence](../../../ansible/roles/platform/tasks/release_root.yml)
- [Root Application](../../../argocd/root.app.yaml)
- [Apps ApplicationSet](../../../argocd/appsets/apps.appset.yaml)
- [Application discovery](../../../validation/sources.py)

## Related pages

- [Talos bootstrap](talos-bootstrap.md)
- [Validation](validation.md)
- [App catalog](../index.md#applications)
