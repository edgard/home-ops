# CrossWatch

Purpose: CrossWatch tracks and synchronizes media watch state.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

Its own configuration claim and HTTPS route are separate from the shared media claim.

## Data and recovery

The values declare a `config` PVC with a `Delete=false` Argo annotation.
Check [restore eligibility](../../architecture/backup-recovery.md) against the
current claim and storage class before changing its lifecycle.

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
