# cert-manager

Purpose: cert-manager issues and renews certificates used by platform components.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

Gateway TLS and webhook certificates depend on its controllers and issuers.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

It is installed during platform bootstrap before dependent webhooks and routes.

## Sources

- [App metadata](../../../../apps/platform-system/cert-manager/app.yaml)
- [Helm values](../../../../apps/platform-system/cert-manager/values.yaml)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Secrets](../../architecture/secrets.md)
- [Networking](../../architecture/networking.md)
