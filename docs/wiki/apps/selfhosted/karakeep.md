# Karakeep

Purpose: Karakeep saves and indexes bookmarks and captured content.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

The app, Chrome, and Meilisearch controllers share an appdata claim and credential ExternalSecret.

## Data and recovery

The values declare app-owned PVC (`data`). Check [restore eligibility](../../architecture/backup-recovery.md) against the current claim and storage class.

## Networking and monitoring

The app values configure a route through the shared Gateway. Check [Gatus values](../../../../apps/platform-system/gatus/values.yaml) for the current explicit uptime target and probe path.

## Operational note

Browser capture, search, and persisted content need separate acceptance checks.

## Sources

- [App metadata](../../../../apps/selfhosted/karakeep/app.yaml)
- [Helm values](../../../../apps/selfhosted/karakeep/values.yaml)
- [Raw manifests](../../../../apps/selfhosted/karakeep/manifests)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Storage](../../architecture/storage.md)
- [Networking](../../architecture/networking.md)
