# Multus

Purpose: Multus enables secondary network attachments.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

Its LAN bridge NetworkAttachmentDefinition is used by selected media and platform workloads.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

A workload annotation and the bridge definition must agree before changing LAN addresses or interfaces.

## Sources

- [App metadata](../../../../apps/kube-system/multus/app.yaml)
- [Helm values](../../../../apps/kube-system/multus/values.yaml)
- [Raw manifests](../../../../apps/kube-system/multus/manifests)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Networking](../../architecture/networking.md)
