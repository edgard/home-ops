# FlareSolverr

Purpose: FlareSolverr provides an internal browser-challenge helper for media services.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

It is an internal service without a declared appdata claim or routed endpoint in this app configuration.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

Consumers must be checked before changing its service or container behavior.

## Sources

- [App metadata](../../../../apps/media/flaresolverr/app.yaml)
- [Helm values](../../../../apps/media/flaresolverr/values.yaml)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Prowlarr](prowlarr.md)
