# Gateway API

Purpose: Gateway API supplies the route CRDs and version metadata.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

Istio Gateway and app HTTPRoutes depend on these CRDs.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

This app primarily carries raw manifests; chart values alone do not describe the installed resources.

## Sources

- [App metadata](../../../../apps/platform-system/gateway-api/app.yaml)
- [Helm values](../../../../apps/platform-system/gateway-api/values.yaml)
- [Raw manifests](../../../../apps/platform-system/gateway-api/manifests)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Networking](../../architecture/networking.md)
