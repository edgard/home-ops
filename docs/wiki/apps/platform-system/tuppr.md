# Tuppr

Purpose: Tuppr manages the declared Kubernetes upgrade target.
Status: current. Reviewed against: `8b3bfc0792a0532ee6d27bea1802d0642db102ae`.

## Dependencies

Validation reads the Kubernetes target from its KubernetesUpgrade manifest;
Tuppr uses the node health check during upgrades.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

Inspect the target manifest and live upgrade preconditions before applying it.
Restoring an older Git revision can restore an older Kubernetes target. The
controller compares exact node versions, so that change can launch node
maintenance. Its native `tuppr.home-operations.com/suspend` annotation pauses the
upgrade resource while the target is reviewed. Remove the annotation only when
the declared target is intended for the running cluster.

## Sources

- [App metadata](../../../../apps/platform-system/tuppr/app.yaml)
- [Helm values](../../../../apps/platform-system/tuppr/values.yaml)
- [Raw manifests](../../../../apps/platform-system/tuppr/manifests)

- [Native suspension and version checks](https://github.com/home-operations/tuppr/tree/0.5.10/internal/controller/kubernetesupgrade)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Talos image factory](../../decisions/talos-image-factory.md)
- [Talos bootstrap](../../architecture/talos-bootstrap.md)
