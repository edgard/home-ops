# GitOps delivery

Purpose: explain how a repository change becomes a cluster application.
Status: current. Reviewed against: `0eb60f6ccc54f3ad28e28fdebd0cf95ca27c1b16`.

Ansible bootstraps foundational services and the Argo CD root application. The
root application installs namespaces, projects, and the `apps` ApplicationSet.
That ApplicationSet reads each `apps/*/*/app.yaml` on `master`, combines its
chart with the matching values file and optional raw manifests, and reconciles
the generated Application. Child Application wave annotations record intended
ordering; independently reconciled ApplicationSet children do not receive a
cross-application readiness barrier from those annotations. Explicit bootstrap
checks, Jobs, and application-specific readiness gates enforce dependencies. A local
edit is not deployable until it is committed and pushed through a PR.

The per-app page records dependencies and operational context; the app metadata,
values, manifests, and generated Application remain the deployment definition.
The [agent workflow](../agent-workflow.md) gives the change and validation loop.

Bootstrap preflight requires a clean checkout matching remote `master`, then
verifies root reconciliation to that captured revision and expected ApplicationSet
children. ESO/store and Argo repository access must be ready before root handoff.

Maintenance must hold the self-healing root before changing ApplicationSet
policies; otherwise root can restore the source policy during the operation.
The [shared-data foundation](../operations/shared-data.md) implements this fence
and records original state for recovery. Its deployment integration is a later
rollout stage.

## Sources

- [Platform bootstrap](../../../ansible/roles/platform/tasks/bootstrap.yml)
- [Root Application](../../../argocd/root.app.yaml)
- [Apps ApplicationSet](../../../argocd/appsets/apps.appset.yaml)
- [Metadata assertions](../../../tests/config/kubernetes/test_sources.py)

## Related pages

- [Talos bootstrap](talos-bootstrap.md)
- [Validation](validation.md)
- [App catalog](../index.md#applications)
