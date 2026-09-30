# Paperless

Purpose: Paperless manages documents, extraction, and optional AI processing.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

The app, GPT, Gotenberg, Tika, and Redis controllers use the appdata claim and credential ExternalSecret.

## Data and recovery

The values declare app-owned PVC (`data`). Check [restore eligibility](../../architecture/backup-recovery.md) against the current claim and storage class.

## Networking and monitoring

The app values configure a route through the shared Gateway. Check [Gatus values](../../../../apps/platform-system/gatus/values.yaml) for the current explicit uptime target and probe path.

## Operational note

Document import, OCR, AI behavior, and recovery have distinct failure modes; test the requested path directly.

## Sources

- [App metadata](../../../../apps/selfhosted/paperless/app.yaml)
- [Helm values](../../../../apps/selfhosted/paperless/values.yaml)
- [Raw manifests](../../../../apps/selfhosted/paperless/manifests)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Storage](../../architecture/storage.md)
- [Networking](../../architecture/networking.md)
