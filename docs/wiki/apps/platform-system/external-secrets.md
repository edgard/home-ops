# External Secrets

Purpose: External Secrets turns Bitwarden references into Kubernetes Secrets.
Status: current. Reviewed against: `6aed89365a1ea1eaca88216fdf9bac132a1e18e5`.

## Dependencies

Platform bootstrap establishes its SDK server, TLS, and ClusterSecretStore before app credentials are consumed.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

ESO and CLI commands share the existing read-only machine account. The store
and SecretSpec reference the same `home-ops` project; the machine account has
read access to exactly that project. SecretSpec scopes control command injection, not account permissions.
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
