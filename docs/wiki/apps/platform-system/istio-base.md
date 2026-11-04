# Istio base

Purpose: Istio base installs foundational Istio resources.
Status: current. Reviewed against: `0eb60f6ccc54f3ad28e28fdebd0cf95ca27c1b16`.

## Dependencies

The Istio control plane depends on this app's resources. Its lower-wave annotation
records intended order; independently reconciled ApplicationSet children still
need explicit prerequisite readiness during bootstrap.

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
