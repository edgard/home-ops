# Istio

Purpose: Istio provides the Gateway controller and shared HTTPS listener.
Status: current. Reviewed against: `74d60b4e0a7607351ba07234d24cd435cfd45f54`.

## Dependencies

It depends on Istio base and Gateway API; raw manifests define the Gateway, certificate, and issuers.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

A healthy control plane does not prove that every HTTPRoute works from clients.

The chart uses Istio's official GHCR release repository. Istio is retiring its
GCP artifact hosting; the [upstream migration notice](https://istio.io/latest/blog/2026/retirement-of-gcp/)
documents the replacement and temporary access-disable tests. The values also
set the image hub to Docker Hub, covering the control plane and generated Gateway
proxy configuration. Keep chart and image sources on the maintained registries
when changing versions.

## Sources

- [App metadata](../../../../apps/platform-system/istio/app.yaml)
- [Helm values](../../../../apps/platform-system/istio/values.yaml)
- [Raw manifests](../../../../apps/platform-system/istio/manifests)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Networking](../../architecture/networking.md)
