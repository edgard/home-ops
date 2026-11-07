# Unpackerr

Purpose: Unpackerr extracts completed downloads for media managers.
Status: current. Reviewed against: `8595d9d1cc7f418c2836b866809c06665e2487dc`.

## Dependencies

It mounts shared media and receives application credentials through an ExternalSecret.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless. It also mounts the shared media claim, which is outside the appdata restore set.

## Networking and monitoring

The deployment is headless: its web listener is explicitly disabled and no
Service or HTTPRoute is enabled. Unpackerr 1 otherwise starts a web UI and API
on all interfaces by default; see the [upstream upgrade guide](https://unpackerr.zip/docs/install/upgrading/).

## Operational note

The shared-media group rule applies; verify consumers after permission or extraction-path changes.

Sonarr and Radarr instances remain configured through environment variables and
secret-backed API keys. Their numbered instance keys are supported by Unpackerr 1.
The golift image uses the pod's user/group settings, not `PUID`/`PGID`.
No persistent config or history is enabled; after restart, Starr polling
rediscovers queued downloads. Enabling UI edits or durable history requires a
separate storage decision and application acceptance check.

## Sources

- [App metadata](../../../../apps/media/unpackerr/app.yaml)
- [Helm values](../../../../apps/media/unpackerr/values.yaml)
- [Raw manifests](../../../../apps/media/unpackerr/manifests)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Storage](../../architecture/storage.md)
- [Shared media group](../../decisions/shared-media-group.md)
