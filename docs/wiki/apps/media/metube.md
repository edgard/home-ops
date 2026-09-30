# MeTube

Purpose: MeTube downloads media and keeps queue and subscription state.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

It stores downloaded files on the shared media claim and its state on a separate appdata claim.

## Data and recovery

The values declare app-owned PVC (`state`). Check [restore eligibility](../../architecture/backup-recovery.md) against the current claim and storage class. It also mounts the shared media claim, which is outside the appdata restore set.

## Networking and monitoring

The app values configure a route through the shared Gateway. Check [Gatus values](../../../../apps/platform-system/gatus/values.yaml) for the current explicit uptime target and probe path.

## Operational note

Check the shared-media group and both persistence paths when changing downloads.
[PR #405](https://github.com/edgard/home-ops/pull/405) records the initial
split between downloads and application state.

## Sources

- [App metadata](../../../../apps/media/metube/app.yaml)
- [Helm values](../../../../apps/media/metube/values.yaml)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Storage](../../architecture/storage.md)
- [Networking](../../architecture/networking.md)
- [Shared media group](../../decisions/shared-media-group.md)
