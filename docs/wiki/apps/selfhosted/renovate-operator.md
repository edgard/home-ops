# Renovate Operator

Purpose: Renovate Operator runs repository dependency-update jobs.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

Its raw RenovateJob and ExternalSecret link the operator to this Git repository.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

Review generated PR behavior and credentials after changing job or operator configuration.

## Sources

- [App metadata](../../../../apps/selfhosted/renovate-operator/app.yaml)
- [Helm values](../../../../apps/selfhosted/renovate-operator/values.yaml)
- [Raw manifests](../../../../apps/selfhosted/renovate-operator/manifests)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
