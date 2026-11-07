# Istio base

Purpose: Istio base installs foundational Istio resources.
Status: current. Reviewed against: `74d60b4e0a7607351ba07234d24cd435cfd45f54`.

## Dependencies

The Istio control plane depends on this lower-wave app.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

Keep CRD and controller ordering intact when changing the platform charts.

Like the control-plane chart, the base chart uses Istio's official GHCR release
repository. The [upstream migration notice](https://istio.io/latest/blog/2026/retirement-of-gcp/)
documents the retirement of the former GCP chart hosting.

## Sources

- [App metadata](../../../../apps/platform-system/istio-base/app.yaml)
- [Helm values](../../../../apps/platform-system/istio-base/values.yaml)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Networking](../../architecture/networking.md)
