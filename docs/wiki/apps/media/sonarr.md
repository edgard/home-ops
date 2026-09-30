# Sonarr

Purpose: Sonarr manages television acquisition and library state.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

It mounts its appdata claim and the shared media claim and uses the HTTPS Gateway.

## Data and recovery

The values declare app-owned PVC (`data`). Check [restore eligibility](../../architecture/backup-recovery.md) against the current claim and storage class. It also mounts the shared media claim, which is outside the appdata restore set.

## Networking and monitoring

The app values configure a route through the shared Gateway. Check [Gatus values](../../../../apps/platform-system/gatus/values.yaml) for the current explicit uptime target and probe path.

## Operational note

Shared media permissions and the qBittorrent/Unpackerr path are cross-service contracts.

## Sources

- [App metadata](../../../../apps/media/sonarr/app.yaml)
- [Helm values](../../../../apps/media/sonarr/values.yaml)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Storage](../../architecture/storage.md)
- [Networking](../../architecture/networking.md)
- [Shared media group](../../decisions/shared-media-group.md)
