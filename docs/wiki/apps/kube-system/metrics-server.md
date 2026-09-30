# metrics-server

Purpose: metrics-server supplies Kubernetes resource metrics.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

It serves Kubernetes API consumers rather than an application route.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

Check API availability and chart settings when changing cluster autoscaling or resource-metric consumers.

## Sources

- [App metadata](../../../../apps/kube-system/metrics-server/app.yaml)
- [Helm values](../../../../apps/kube-system/metrics-server/values.yaml)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Validation](../../architecture/validation.md)
