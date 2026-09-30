# Istio base

Purpose: Istio base installs foundational Istio resources.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

The Istio control plane depends on this lower-wave app.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

Keep CRD and controller ordering intact when changing the platform charts.

## Sources

- [App metadata](../../../../apps/platform-system/istio-base/app.yaml)
- [Helm values](../../../../apps/platform-system/istio-base/values.yaml)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Networking](../../architecture/networking.md)
