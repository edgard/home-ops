# GitOps delivery

Purpose: explain how a repository change becomes a cluster application.
Status: current. Reviewed against: `e66f8dac017406e0b72605aa16d5f7862aaa0c8a`.

Ansible bootstraps foundational services and the Argo CD root application. The
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
children. ESO/store and Argo repository access must be ready before root handoff.

## Sources

- [Platform bootstrap](../../../ansible/roles/platform/tasks/bootstrap.yml)
- [Root Application](../../../argocd/root.app.yaml)
- [Apps ApplicationSet](../../../argocd/appsets/apps.appset.yaml)
- [Metadata assertions](../../../tests/config/kubernetes/test_sources.py)

## Related pages

- [Talos bootstrap](talos-bootstrap.md)
- [Validation](validation.md)
- [App catalog](../index.md#applications)
