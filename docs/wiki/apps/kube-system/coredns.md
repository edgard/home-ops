# CoreDNS

Purpose: CoreDNS resolves cluster names and forwards the homelab zone.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

Depends on the Kubernetes DNS service and the k8s-gateway service configured in its Corefile.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

Its repository ConfigMap is the DNS configuration; route changes can affect homelab name resolution.

## Sources

- [App metadata](../../../../apps/kube-system/coredns/app.yaml)
- [Helm values](../../../../apps/kube-system/coredns/values.yaml)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [k8s-gateway](k8s-gateway.md)
- [Networking](../../architecture/networking.md)
