# Bazarr

Purpose: Bazarr manages subtitles for the media library.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

Shares the media claim with other media apps and uses an appdata claim for its own state.

## Data and recovery

The values declare app-owned PVC (`data`). Check [restore eligibility](../../architecture/backup-recovery.md) against the current claim and storage class. It also mounts the shared media claim, which is outside the appdata restore set.

## Networking and monitoring

The app values configure a route through the shared Gateway. Check [Gatus values](../../../../apps/platform-system/gatus/values.yaml) for the current explicit uptime target and probe path.

## Operational note

The shared claim ownership rule applies even when only subtitles are changed.

## Sources

- [App metadata](../../../../apps/media/bazarr/app.yaml)
- [Helm values](../../../../apps/media/bazarr/values.yaml)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Storage](../../architecture/storage.md)
- [Networking](../../architecture/networking.md)
- [Shared media group](../../decisions/shared-media-group.md)
