# CrossWatch

Purpose: CrossWatch tracks and synchronizes media watch state.
Status: current. Reviewed against: `b1218c66872fdb2d829e635b7e76b82123fd5b21`.

## Dependencies

Its own configuration claim and HTTPS route are separate from the shared media claim.

## Data and recovery

The values declare a `config` PVC with a `Delete=false` Argo annotation.
Check [restore eligibility](../../architecture/backup-recovery.md) against the
current claim and storage class before changing its lifecycle.

Tracker-format upgrades can migrate persistent data. The
[v0.14.2 release notes](https://github.com/cenodude/CrossWatch/releases/tag/v0.14.2)
describe automatic JSON-to-database migration and retention of original JSON and
older snapshots in `json-backup-*` directories. Preserve the whole `/config`
claim before changing versions; rolling back the image alone is not a documented
database rollback procedure. The same release changes the default internal
snapshot count from 64 to 14 per feature, with up to 30 days of retention.

## Networking and monitoring

The app values configure a route through the shared Gateway. Check [Gatus values](../../../../apps/platform-system/gatus/values.yaml) for the current explicit uptime target and probe path.

## Operational note

The configured `/healthz` endpoint is an uptime contract. The routed service
was exposed after authentication checks in
[PR #387](https://github.com/edgard/home-ops/pull/387); review authentication
and Jellyfin integration together.

## Sources

- [App metadata](../../../../apps/media/crosswatch/app.yaml)
- [Helm values](../../../../apps/media/crosswatch/values.yaml)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Storage](../../architecture/storage.md)
- [Networking](../../architecture/networking.md)
- [Jellyfin cutover](../../decisions/jellyfin-cutover.md)
- [Jellyfin](jellyfin.md)
