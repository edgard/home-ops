# Tuppr

Purpose: Tuppr applies the declared Talos and Kubernetes upgrade targets.
Status: current. Reviewed against: `46c0ab2a` and this revision.

## Dependencies

Bootstrap reads the Talos and Kubernetes versions from their upgrade manifests.
The controller namespace has `os:admin` Talos API access through the committed
machine configuration. Tuppr coordinates the two upgrade types so they do not
run concurrently.

The Talos plan uses native defaults, including the built-in cluster health gate
and installer pre-pull. It has no custom health checks or backup/storage hooks.
The existing Kubernetes plan requires the named physical node to be Ready and
the current OpenEBS node DaemonSet generation to have one updated Ready pod.

## Data and recovery

The controller has no app-owned PVC; upgrade state is recorded in Kubernetes
resources. Talos upgrades preserve the Factory installer path and schematic
from the node's configuration, including its system extensions. After a verified
upgrade, the controller attempts to update the configured installer; failures
are logged and do not fail the run.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

Argo CD applies merged target changes and Tuppr starts immediately; there is no
maintenance window. Renovate groups the Talos target with the bootstrap
installer image. Patches and minor updates can automerge after CI; major and
rollback updates require review. Restoring an older Git revision can restore an older
upgrade target and launch maintenance again.

On this single-node cluster, a Talos upgrade takes the whole homelab offline
during reboot. Tuppr automatically permits its upgrade Job on the target node
and uses `--wait=false` and `--drain=false`. After restart it verifies the
node's version and readiness, accepting a reboot-killed Job when the node has
actually upgraded. The chart tolerates a cordoned node so the controller can
restart there and uncordon it. No placement override is needed.

Inspect progress and events with:

```sh
kubectl --context admin@homelab get talosupgrade,kubernetesupgrade
kubectl --context admin@homelab describe talosupgrade talos
kubectl --context admin@homelab -n platform-system logs deployment/tuppr
```

A failed run requires operator action. Diagnose its status, events and controller
logs before retrying. Tuppr's native reset annotation starts a new attempt
without changing the target:

```sh
kubectl --context admin@homelab annotate talosupgrade talos \
  tuppr.home-operations.com/reset="$(date -u +%s)" --overwrite
```

For emergency intervention with `talosctl`, first add the
`tuppr.home-operations.com/suspend` annotation to **both** upgrade resources in
Git. Wait for each resource to acknowledge its current generation with
`Progressing=False`, reason `Suspended`, and for existing upgrade Jobs and Pods
to finish. Suspension prevents new reconciliation; it does not cancel Jobs.
Keep the Git targets aligned with the intended versions. Remove the suspension
in Git after checking the resulting versions and node readiness. Routine
upgrades have no manual Task or Ansible upgrade path.

## Sources

- [App metadata](../../../../apps/platform-system/tuppr/app.yaml)
- [Helm values](../../../../apps/platform-system/tuppr/values.yaml)
- [Talos target](../../../../apps/platform-system/tuppr/manifests/tuppr-talos.talosupgrade.yaml) and [Kubernetes target](../../../../apps/platform-system/tuppr/manifests/tuppr-kubernetes.kubernetesupgrade.yaml)
- [Talos API access](../../../../ansible/roles/talos/files/controlplane-patch.yaml)
- [Bootstrap target loading](../../../../ansible/roles/talos/tasks/validate_generation.yml)
- [Single-node upgrade implementation](https://github.com/home-operations/tuppr/blob/0.5.14/internal/controller/talosupgrade/jobs.go) and [regression tests](https://github.com/home-operations/tuppr/blob/0.5.14/internal/controller/talosupgrade/controller_test.go)
- [Controller tolerations](https://github.com/home-operations/tuppr/blob/0.5.14/charts/tuppr/values.yaml), [coordination](https://github.com/home-operations/tuppr/blob/0.5.14/docs/src/content/docs/coordination.md), and [native operations](https://github.com/home-operations/tuppr/blob/0.5.14/docs/src/content/docs/operations.md)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Talos image factory](../../decisions/talos-image-factory.md)
- [Talos bootstrap](../../architecture/talos-bootstrap.md)
