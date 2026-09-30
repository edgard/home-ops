# NFS provisioner

Purpose: The NFS CSI provisioner supplies default appdata storage and static shared media resources.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

It depends on the external NFS server and is a prerequisite for PVC-backed applications.

## Data and recovery

The chart configures dynamic appdata provisioning. Raw manifests define the
static shared media PV and PVC; those resources are not an app-owned claim of
the provisioner.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

The media PV/PVC is separate from dynamically provisioned appdata and the Restic repository.

## Sources

- [App metadata](../../../../apps/kube-system/nfs-provisioner/app.yaml)
- [Helm values](../../../../apps/kube-system/nfs-provisioner/values.yaml)
- [Raw manifests](../../../../apps/kube-system/nfs-provisioner/manifests)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Shared media group](../../decisions/shared-media-group.md)
- [Storage](../../architecture/storage.md)
