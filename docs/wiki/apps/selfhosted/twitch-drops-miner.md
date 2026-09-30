# Twitch Drops Miner

Purpose: Twitch Drops Miner runs a persistent streaming-reward session.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

It uses an appdata claim and a routed interface.

## Data and recovery

The values declare app-owned PVC (`data`). Check [restore eligibility](../../architecture/backup-recovery.md) against the current claim and storage class.

## Networking and monitoring

The app values configure a route through the shared Gateway. Check [Gatus values](../../../../apps/platform-system/gatus/values.yaml) for the current explicit uptime target and probe path.

## Operational note

Session state and the routed UI should both be checked after image or storage changes.

## Sources

- [App metadata](../../../../apps/selfhosted/twitch-drops-miner/app.yaml)
- [Helm values](../../../../apps/selfhosted/twitch-drops-miner/values.yaml)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Storage](../../architecture/storage.md)
- [Networking](../../architecture/networking.md)
