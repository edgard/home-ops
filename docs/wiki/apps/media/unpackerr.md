# Unpackerr

Purpose: Unpackerr extracts completed downloads for media managers.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

It mounts shared media and receives application credentials through an ExternalSecret.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless. It also mounts the shared media claim, which is outside the appdata restore set.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

The shared-media group rule applies; verify consumers after permission or extraction-path changes.

## Sources

- [App metadata](../../../../apps/media/unpackerr/app.yaml)
- [Helm values](../../../../apps/media/unpackerr/values.yaml)
- [Raw manifests](../../../../apps/media/unpackerr/manifests)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Storage](../../architecture/storage.md)
- [Shared media group](../../decisions/shared-media-group.md)
