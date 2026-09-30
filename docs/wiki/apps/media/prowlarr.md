# Prowlarr

Purpose: Prowlarr manages indexer integration for the media stack.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

It uses appdata storage and a Gateway route; other media services consume its configuration.

## Data and recovery

The values declare app-owned PVC (`data`). Check [restore eligibility](../../architecture/backup-recovery.md) against the current claim and storage class.

## Networking and monitoring

The app values configure a route through the shared Gateway. Check [Gatus values](../../../../apps/platform-system/gatus/values.yaml) for the current explicit uptime target and probe path.

## Operational note

Changes to indexer wiring should be verified with the consuming services.

## Sources

- [App metadata](../../../../apps/media/prowlarr/app.yaml)
- [Helm values](../../../../apps/media/prowlarr/values.yaml)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Storage](../../architecture/storage.md)
- [Networking](../../architecture/networking.md)
- [FlareSolverr](flaresolverr.md)
