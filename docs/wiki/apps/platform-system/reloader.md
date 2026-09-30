# Reloader

Purpose: Reloader restarts workloads when referenced configuration changes.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

Controllers in other apps opt in through annotations.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

A Reloader rollout still needs application-level checks for sensitive or shared-storage changes.

## Sources

- [App metadata](../../../../apps/platform-system/reloader/app.yaml)
- [Helm values](../../../../apps/platform-system/reloader/values.yaml)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Validation](../../architecture/validation.md)
