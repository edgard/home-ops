# Recyclarr

Purpose: Recyclarr synchronizes declarative quality and naming configuration into media managers.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

Its ConfigMap and ExternalSecret supply configuration and credentials; a claim stores application state.

## Data and recovery

The values declare app-owned PVC (`data`). Check [restore eligibility](../../architecture/backup-recovery.md) against the current claim and storage class.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

Review the Radarr and Sonarr targets, especially naming conventions, when changing its config.

## Sources

- [App metadata](../../../../apps/media/recyclarr/app.yaml)
- [Helm values](../../../../apps/media/recyclarr/values.yaml)
- [Raw manifests](../../../../apps/media/recyclarr/manifests)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Storage](../../architecture/storage.md)
- [Jellyfin](jellyfin.md)
- [Sonarr](sonarr.md)
- [Radarr](radarr.md)
