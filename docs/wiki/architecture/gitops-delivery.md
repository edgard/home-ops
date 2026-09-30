# GitOps delivery

Purpose: explain how a repository change becomes a cluster application.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

Ansible bootstraps foundational services and the Argo CD root application. The
root application installs namespaces, projects, and the `apps` ApplicationSet.
That ApplicationSet reads each `apps/*/*/app.yaml` on `master`, combines its
chart with the matching values file and optional raw manifests, and reconciles
the generated Application. Sync waves order prerequisites before apps. A local
edit is not deployable until it is committed and pushed through a PR.

The per-app page records dependencies and operational context; the app metadata,
values, manifests, and generated Application remain the deployment definition.
The [agent workflow](../agent-workflow.md) gives the change and validation loop.

## Sources

- [Platform bootstrap](../../../ansible/roles/platform/tasks/bootstrap.yml)
- [Root Application](../../../argocd/root.app.yaml)
- [Apps ApplicationSet](../../../argocd/appsets/apps.appset.yaml)
- [Metadata policy](../../../policy/metadata/app_metadata.rego)

## Related pages

- [Talos bootstrap](talos-bootstrap.md)
- [Validation](validation.md)
- [App catalog](../index.md#applications)
