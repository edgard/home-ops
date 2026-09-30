# Scrypted

Purpose: Scrypted hosts home video integrations.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

Uses the shared Gateway and NFS appdata provisioning.

## Data and recovery

The values declare app-owned PVC (`data`). Check [restore eligibility](../../architecture/backup-recovery.md) against the current claim and storage class.

## Networking and monitoring

The app values configure a route through the shared Gateway. Check [Gatus values](../../../../apps/platform-system/gatus/values.yaml) for the current explicit uptime target and probe path.

## Operational note

Persistent application state is distinct from any camera or device data outside this repository.

## Sources

- [App metadata](../../../../apps/home-automation/scrypted/app.yaml)
- [Helm values](../../../../apps/home-automation/scrypted/values.yaml)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Storage](../../architecture/storage.md)
- [Networking](../../architecture/networking.md)
