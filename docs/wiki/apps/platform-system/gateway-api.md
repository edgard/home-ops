# Gateway API

Purpose: Gateway API supplies the route CRDs and version metadata.
Status: current. Reviewed against: `8595d9d1cc7f418c2836b866809c06665e2487dc`.

## Dependencies

Istio Gateway and app HTTPRoutes depend on these CRDs.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

This app primarily carries raw manifests; chart values alone do not describe the installed resources.

The [vendored standard bundle](../../../../apps/platform-system/gateway-api/manifests/gateway-api-crds.yaml)
includes the `safe-upgrades.gateway.networking.k8s.io` admission policy. Its
minimum bundle version advances with upgrades, so reverting the Git commit alone
can be rejected when rolling back. Inspect that policy and verify that the older
CRDs can still serve every stored resource version before planning a downgrade.
The upstream bundle requires deliberately removing the policy to permit an older
bundle; coordinate GitOps reconciliation so it does not recreate the policy
during that operation. Do not delete CRDs to bypass the guard: doing so deletes
their custom resources, including Gateways and routes. The
[upstream standard bundle](https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.7.0/standard-install.yaml)
contains the policy's validation rules and downgrade instructions.

## Sources

- [App metadata](../../../../apps/platform-system/gateway-api/app.yaml)
- [Helm values](../../../../apps/platform-system/gateway-api/values.yaml)
- [Raw manifests](../../../../apps/platform-system/gateway-api/manifests)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Networking](../../architecture/networking.md)
