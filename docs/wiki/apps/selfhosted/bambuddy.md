# Bambuddy

Purpose: Bambuddy manages 3D-printer related application data.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

It uses an appdata claim and a temporary log volume behind the shared Gateway.

## Data and recovery

The values declare app-owned PVC (`data`). Check [restore eligibility](../../architecture/backup-recovery.md) against the current claim and storage class.

## Networking and monitoring

The app values configure a route through the shared Gateway. Check [Gatus values](../../../../apps/platform-system/gatus/values.yaml) for the current explicit uptime target and probe path.

## Operational note

Temporary logs and persistent application data have different recovery behavior.

## Sources

- [App metadata](../../../../apps/selfhosted/bambuddy/app.yaml)
- [Helm values](../../../../apps/selfhosted/bambuddy/values.yaml)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Storage](../../architecture/storage.md)
- [Networking](../../architecture/networking.md)
