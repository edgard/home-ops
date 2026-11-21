# OpenEBS ZFS LocalPV

Purpose: describe storage dependencies, recovery and monitoring for OpenEBS ZFS LocalPV.
Status: current. Reviewed against: `e0ffdb032870a9272c7abd691788e9b4e4b48ee1` and this revision.

The CSI node verifies the physical pool GUID against the immutable foundation
record before accepting provisioning requests. The controller and node plugin
depend on the Talos ZFS extension and the imported `dpool/k8s` filesystem.
The default class supports same-node sharing for namespace backup Pods. It
retains appdata volumes. The media PV uses the existing shared filesystem.
Neither component exposes a LAN service.

## Sources

- [Application](../../../../apps/kube-system/zfs-localpv/app.yaml)
- [Values](../../../../apps/kube-system/zfs-localpv/values.yaml)
- [Manifests](../../../../apps/kube-system/zfs-localpv/manifests)

## Related pages

- [Storage](../../architecture/storage.md)
- [Talos bootstrap](../../architecture/talos-bootstrap.md)
