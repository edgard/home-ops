# External DNS

Purpose: External DNS synchronizes route-derived names to the local DNS provider.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

It watches HTTPRoutes and uses a credential from External Secrets for the UniFi webhook.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

DNS record propagation and client caching require separate checks from route readiness.

## Sources

- [App metadata](../../../../apps/platform-system/external-dns/app.yaml)
- [Helm values](../../../../apps/platform-system/external-dns/values.yaml)
- [Raw manifests](../../../../apps/platform-system/external-dns/manifests)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Networking](../../architecture/networking.md)
- [Secrets](../../architecture/secrets.md)
