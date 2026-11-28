# Recyclarr

Purpose: Recyclarr synchronizes declarative quality and naming configuration into media managers.
Status: current. Reviewed against: `4e54fc81ff2e422f7fee1ba8313ee1d99dfe0d8e` and this revision.

## Dependencies

The [ConfigMap](../../../../apps/media/recyclarr/manifests/recyclarr-config.configmap.yaml)
supplies the Radarr and Sonarr sync rules in `recyclarr.yml` and the daily
server schedule in `settings.yml`. The
[ExternalSecret](../../../../apps/media/recyclarr/manifests/recyclarr-credentials.externalsecret.yaml)
supplies the two client credentials and a separate server API key from Bitwarden.
Create the `recyclarr_api_key` item in the `home-ops` project with a random value
of at least 32 characters before deploying or restoring the app.

## Data and recovery

The values declare app-owned PVC (`data`). Check [restore eligibility](../../architecture/backup-recovery.md) against the current claim and storage class.

## Networking and monitoring

The API and management listeners bind to loopback inside the pod. The app
declares no Service or route.

## Operational note

Review the Radarr and Sonarr targets, especially naming conventions, when changing its config.

## Sources

- [App metadata](../../../../apps/media/recyclarr/app.yaml)
- [Helm values](../../../../apps/media/recyclarr/values.yaml)
- [Raw manifests](../../../../apps/media/recyclarr/manifests)
- [Recyclarr v9 upgrade guide](https://recyclarr.dev/guide/upgrade-guide/v9.0/) — server API key and schedule migration.

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Storage](../../architecture/storage.md)
- [Secrets maintenance](../../operations/secrets-maintenance.md)
- [Jellyfin](jellyfin.md)
- [Sonarr](sonarr.md)
- [Radarr](radarr.md)
