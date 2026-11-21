# OpenEBS ZFS LocalPV

Purpose: describe storage dependencies, recovery and monitoring for OpenEBS ZFS LocalPV.
Status: current. Reviewed against: `d80872c8700249ef67aa42919e297c37e75faef3`.

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
- [TrueNAS migration](../../operations/truenas-migration.md)
