# Changedetection

Purpose: Changedetection tracks changes to selected pages.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

Its main app and browser sidecar share the app deployment; an appdata claim and ExternalSecret support state and credentials.

## Data and recovery

The values declare app-owned PVC (`data`). Check [restore eligibility](../../architecture/backup-recovery.md) against the current claim and storage class.

## Networking and monitoring

The [app values](../../../../apps/selfhosted/changedetection/values.yaml) define the Gateway route and declare its Blackbox probe URL on the web Service.

## Operational note

Check browser-sidecar connectivity and persisted watches, not only the HTTP route.

## Sources

- [App metadata](../../../../apps/selfhosted/changedetection/app.yaml)
- [Helm values](../../../../apps/selfhosted/changedetection/values.yaml)
- [Raw manifests](../../../../apps/selfhosted/changedetection/manifests)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Storage](../../architecture/storage.md)
- [Networking](../../architecture/networking.md)
