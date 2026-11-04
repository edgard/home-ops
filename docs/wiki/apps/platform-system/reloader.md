# Reloader

Purpose: Reloader restarts workloads when referenced configuration changes.
Status: current. Reviewed against: `0eb60f6ccc54f3ad28e28fdebd0cf95ca27c1b16`.

## Dependencies

Controllers in other apps opt in through annotations.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

A Reloader rollout still needs application-level checks for sensitive or shared-storage changes.

The [shared-data coordinator](../../operations/shared-data.md) records replica
counts and verifies writer Pods are stopped while configuration and credential
changes occur. Any independently triggered rollout must remain within that
maintenance fence.

## Sources

- [App metadata](../../../../apps/platform-system/reloader/app.yaml)
- [Helm values](../../../../apps/platform-system/reloader/values.yaml)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Validation](../../architecture/validation.md)
