# k8s-gateway

Purpose: k8s-gateway answers DNS for HTTPRoute names in the homelab zone.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

CoreDNS forwards the zone to its static service address; unknown names fall through to the local resolver.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

The static service address is a cross-app contract with CoreDNS, not an independent setting.

## Sources

- [App metadata](../../../../apps/kube-system/k8s-gateway/app.yaml)
- [Helm values](../../../../apps/kube-system/k8s-gateway/values.yaml)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [CoreDNS](coredns.md)
- [Networking](../../architecture/networking.md)
