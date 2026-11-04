# k8tz

Purpose: k8tz sets timezone behavior for workloads through an admission webhook.
Status: current. Reviewed against: `0eb60f6ccc54f3ad28e28fdebd0cf95ca27c1b16`.

## Dependencies

Its webhook certificate comes from cert-manager, with raw manifests that wait for certificate prerequisites.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

Its webhook failure policy protects admission availability. The sync-wave
annotation records intended order; explicit bootstrap checks provide dependency
gating across independently reconciled Applications.

The app metadata selects the official upstream Helm repository. Chart versions
remain pinned independently of the repository URL.

## Sources

- [App metadata](../../../../apps/kube-system/k8tz/app.yaml)
- [Helm values](../../../../apps/kube-system/k8tz/values.yaml)
- [Raw manifests](../../../../apps/kube-system/k8tz/manifests)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Talos bootstrap](../../architecture/talos-bootstrap.md)
