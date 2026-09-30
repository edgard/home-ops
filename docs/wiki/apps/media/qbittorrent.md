# qBittorrent

Purpose: qBittorrent provides downloads through a Gluetun VPN sidecar.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

It mounts appdata, shared media, a node TUN device, and an ExternalSecret for VPN credentials.

## Data and recovery

The values declare app-owned PVC (`data`). Check [restore eligibility](../../architecture/backup-recovery.md) against the current claim and storage class. It also mounts the shared media claim, which is outside the appdata restore set. The host path mount (`dev-net-tun`) depends on the node.

## Networking and monitoring

The app values configure a route through the shared Gateway. Check [Gatus values](../../../../apps/platform-system/gatus/values.yaml) for the current explicit uptime target and probe path.

## Operational note

Gluetun HTTP liveness detects unhealthy VPN state after the failure described
in [PR #383](https://github.com/edgard/home-ops/pull/383). Verify isolation
and reconnect behavior when editing probes or networking.

## Sources

- [App metadata](../../../../apps/media/qbittorrent/app.yaml)
- [Helm values](../../../../apps/media/qbittorrent/values.yaml)
- [Raw manifests](../../../../apps/media/qbittorrent/manifests)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Storage](../../architecture/storage.md)
- [Networking](../../architecture/networking.md)
- [Gluetun health](../../decisions/gluetun-health.md)
- [Shared media group](../../decisions/shared-media-group.md)
