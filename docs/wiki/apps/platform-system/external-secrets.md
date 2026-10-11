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

ESO uses an application-only machine account, separate from the operator account.
The shared store restricts consumers to the namespaces in its conditions; those
namespaces are not isolated from each other. Bootstrap waits for store readiness
before Argo handoff. [Token replacement](../../operations/secrets-maintenance.md)
validates access and waits for fresh reconciliation with rollback on failure.

## Sources

- [App metadata](../../../../apps/platform-system/external-secrets/app.yaml)
- [Helm values](../../../../apps/platform-system/external-secrets/values.yaml)
- [Raw manifests](../../../../apps/platform-system/external-secrets/manifests)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Secrets](../../architecture/secrets.md)
