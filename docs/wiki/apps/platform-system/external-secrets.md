# External Secrets

Purpose: External Secrets turns Bitwarden references into Kubernetes Secrets.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

Platform bootstrap establishes its SDK server, TLS, and ClusterSecretStore before app credentials are consumed.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

The shared store is a security boundary; review consumers and credential scope together.

## Sources

- [App metadata](../../../../apps/platform-system/external-secrets/app.yaml)
- [Helm values](../../../../apps/platform-system/external-secrets/values.yaml)
- [Raw manifests](../../../../apps/platform-system/external-secrets/manifests)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Secrets](../../architecture/secrets.md)
