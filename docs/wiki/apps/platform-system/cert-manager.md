# cert-manager

Purpose: cert-manager issues and renews certificates used by platform components.
Status: current. Reviewed against: `b898924ceaf8be0a1b00e20fed8f57369259f669`.

## Dependencies

The app owns the gateway wildcard Certificate, its production and staging ACME
Issuers, and the ExternalSecret that supplies the Cloudflare DNS challenge token.
Envoy references the resulting TLS Secret in the same namespace.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

It is installed during platform bootstrap before dependent webhooks and routes.

## Sources

- [App metadata](../../../../apps/platform-system/cert-manager/app.yaml)
- [Helm values](../../../../apps/platform-system/cert-manager/values.yaml)
- [Gateway certificate and issuers](../../../../apps/platform-system/cert-manager/manifests)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Secrets](../../architecture/secrets.md)
- [Networking](../../architecture/networking.md)
