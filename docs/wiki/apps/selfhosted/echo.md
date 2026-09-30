# Echo

Purpose: Echo is a small routed HTTP diagnostic service.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

It uses the shared Gateway without an appdata claim in values.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

The app values configure a route through the shared Gateway. Check [Gatus values](../../../../apps/platform-system/gatus/values.yaml) for the current explicit uptime target and probe path.

## Operational note

The response is useful for route checks but does not validate other applications.

## Sources

- [App metadata](../../../../apps/selfhosted/echo/app.yaml)
- [Helm values](../../../../apps/selfhosted/echo/values.yaml)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Networking](../../architecture/networking.md)
