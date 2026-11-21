# Tuppr

Purpose: Tuppr manages the declared Kubernetes upgrade target.
Status: current. Reviewed against: `09ff984c2258c4403ef203631fd580106f839e53` and this revision.

## Dependencies

Validation reads the Kubernetes target from its KubernetesUpgrade manifest;
Tuppr requires the named physical node to be Ready and the current OpenEBS
node DaemonSet generation to have one updated Ready pod. Its storage init
container checks the imported pool GUID before the CSI pod can become Ready.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

Inspect the target manifest and live upgrade preconditions before applying it.
Restoring an older Git revision can restore an older Kubernetes target. The
controller compares exact node versions, so that change can launch node
maintenance. For an ordinary upgrade, merge the intended KubernetesUpgrade
version and let Tuppr perform it.

For a manual upgrade, add the `tuppr.home-operations.com/suspend` annotation
to the KubernetesUpgrade in Git before changing the target. Keep it present
when merging the target version. Wait for the live resource to show
`Progressing=False` with reason `Suspended` for its current generation and
for any existing upgrade Jobs and Pods to finish. Suspension pauses new
reconciliation and leaves previously created Jobs to finish.

Run `task talos:upgrade-k8s` with the merged checkout. The task checks
the suspended live target against the repository before running
`talosctl upgrade-k8s`. An optional `K8S_VERSION` must match the committed
version. After checking the API server and kubelet versions and node
readiness, remove the suspension in Git to resume ordinary reconciliation.

## Sources

- [App metadata](../../../../apps/platform-system/tuppr/app.yaml)
- [Helm values](../../../../apps/platform-system/tuppr/values.yaml)
- [Raw manifests](../../../../apps/platform-system/tuppr/manifests)
- [Manual upgrade checks](../../../../ansible/roles/talos/tasks/upgrade_k8s.yml)
- [Native suspension and version checks](https://github.com/home-operations/tuppr/tree/0.5.14/internal/controller/kubernetesupgrade)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Talos image factory](../../decisions/talos-image-factory.md)
- [Talos bootstrap](../../architecture/talos-bootstrap.md)
