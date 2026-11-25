# metrics-server

Purpose: metrics-server supplies Kubernetes resource metrics.
Status: current. Reviewed against: `15c898cf` and this revision.

## Dependencies

It serves Kubernetes API consumers rather than an application route. Kubelet
serving certificates must be issued by the cluster CA through Talos rotation
and the [CSR approver](kubelet-csr-approver.md). The values explicitly select
the mounted cluster CA; kubelet TLS verification remains enabled.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

Check API availability and chart settings when changing cluster autoscaling or resource-metric consumers.
After certificate changes, verify `kubectl top pods -A` and the availability
of `v1beta1.metrics.k8s.io`. Pending serving CSRs can leave the process healthy
while resource collection fails.

## Sources

- [App metadata](../../../../apps/kube-system/metrics-server/app.yaml)
- [Helm values](../../../../apps/kube-system/metrics-server/values.yaml)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Validation](../../architecture/validation.md)
- [Kubelet CSR approver](kubelet-csr-approver.md)
