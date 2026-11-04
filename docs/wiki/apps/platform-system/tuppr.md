# Tuppr

Purpose: Tuppr manages the declared Kubernetes upgrade target.
Status: current. Reviewed against: `0eb60f6ccc54f3ad28e28fdebd0cf95ca27c1b16`.

## Dependencies

Validation reads the Kubernetes target from its KubernetesUpgrade manifest;
Tuppr uses the node health check during upgrades.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

Inspect the target manifest and live upgrade preconditions before treating the version as ready to apply.

The [shared-data coordinator](../../operations/shared-data.md) holds Tuppr during
maintenance and checks its independently running upgrade Jobs and Pods. Stopping
the controller alone does not stop an already-created node-upgrade Job.

## Sources

- [App metadata](../../../../apps/platform-system/tuppr/app.yaml)
- [Helm values](../../../../apps/platform-system/tuppr/values.yaml)
- [Raw manifests](../../../../apps/platform-system/tuppr/manifests)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Talos image factory](../../decisions/talos-image-factory.md)
- [Talos bootstrap](../../architecture/talos-bootstrap.md)
