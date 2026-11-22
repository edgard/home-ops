# Home Assistant

Purpose: Home Assistant hosts home automation state and integrations.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

Uses the shared Gateway, OpenEBS ZFS appdata class, and a repository ConfigMap for configuration.

## Data and recovery

The values declare app-owned PVC (`data`). Check [restore eligibility](../../architecture/backup-recovery.md) against the current claim and storage class.

## Networking and monitoring

The [app values](../../../../apps/home-automation/homeassistant/values.yaml) define the Gateway route and declare its Blackbox probe URL on the web Service.

## Operational note

Review the ConfigMap and persistent state together when changing integrations.

## Sources

- [App metadata](../../../../apps/home-automation/homeassistant/app.yaml)
- [Helm values](../../../../apps/home-automation/homeassistant/values.yaml)
- [Raw manifests](../../../../apps/home-automation/homeassistant/manifests)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Storage](../../architecture/storage.md)
- [Networking](../../architecture/networking.md)
