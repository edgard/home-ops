# Jellyfin

Purpose: Jellyfin serves the media library.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

It uses a configuration claim, temporary cache, read-only shared media, the HTTPS Gateway, and direct LAN networking.

## Data and recovery

The values declare app-owned PVC (`config`). Check [restore eligibility](../../architecture/backup-recovery.md) against the current claim and storage class. It also mounts the shared media claim, which is outside the appdata restore set.

## Networking and monitoring

The app values configure a route through the shared Gateway. Check [Gatus values](../../../../apps/platform-system/gatus/values.yaml) for the current explicit uptime target and probe path.

## Operational note

TCP liveness and HTTP readiness are intentionally separate so library scans do
not trigger needless restarts, as recorded in
[PR #412](https://github.com/edgard/home-ops/pull/412).

## Sources

- [App metadata](../../../../apps/media/jellyfin/app.yaml)
- [Helm values](../../../../apps/media/jellyfin/values.yaml)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Storage](../../architecture/storage.md)
- [Networking](../../architecture/networking.md)
- [Jellyfin cutover](../../decisions/jellyfin-cutover.md)
