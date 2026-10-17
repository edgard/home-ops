# Gatus

Purpose: Gatus checks explicit app, DNS, and internet targets and sends Telegram alerts.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

It relies on routes, DNS, and a credential ExternalSecret but does not have persistent status storage.

## Data and recovery

The [values](../../../../apps/platform-system/gatus/values.yaml) select memory
storage and disable persistence. Uptime history is lost when this instance
restarts.

## Networking and monitoring

The status page is routed through the shared Gateway. Gatus targets are
configured in [its values](../../../../apps/platform-system/gatus/values.yaml);
the status page does not monitor itself.

## Operational note

A complete single-node outage cannot be reported by this in-cluster checker.

## Sources

- [App metadata](../../../../apps/platform-system/gatus/app.yaml)
- [Helm values](../../../../apps/platform-system/gatus/values.yaml)
- [Raw manifests](../../../../apps/platform-system/gatus/manifests)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Networking](../../architecture/networking.md)
- [Gatus transition](../../decisions/gatus-transition.md)
- [Uptime monitoring](../../architecture/uptime.md)
