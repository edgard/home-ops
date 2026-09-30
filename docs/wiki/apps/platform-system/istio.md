# Istio

Purpose: Istio provides the Gateway controller and shared HTTPS listener.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

It depends on Istio base and Gateway API; raw manifests define the Gateway, certificate, and issuers.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

A healthy control plane does not prove that every HTTPRoute works from clients.

## Sources

- [App metadata](../../../../apps/platform-system/istio/app.yaml)
- [Helm values](../../../../apps/platform-system/istio/values.yaml)
- [Raw manifests](../../../../apps/platform-system/istio/manifests)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Networking](../../architecture/networking.md)
