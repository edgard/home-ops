# k8tz

Purpose: k8tz sets timezone behavior for workloads through an admission webhook.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

Its webhook certificate comes from cert-manager, with raw manifests that wait for certificate prerequisites.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

Its sync wave and webhook failure policy protect bootstrap order and availability.

## Sources

- [App metadata](../../../../apps/kube-system/k8tz/app.yaml)
- [Helm values](../../../../apps/kube-system/k8tz/values.yaml)
- [Raw manifests](../../../../apps/kube-system/k8tz/manifests)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Talos bootstrap](../../architecture/talos-bootstrap.md)
