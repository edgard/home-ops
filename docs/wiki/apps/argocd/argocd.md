# Argo CD

Purpose: Argo CD reconciles the applications generated from repository metadata.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

Platform bootstrap installs Argo CD after its storage, networking, certificate, and secret prerequisites.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

The app values configure a route through the shared Gateway. Check [Gatus values](../../../../apps/platform-system/gatus/values.yaml) for the current explicit uptime target and probe path.

## Operational note

Its root Application and repository credential ExternalSecrets are part of the bootstrap path; changes to discovery need ApplicationSet validation.

## Sources

- [App metadata](../../../../apps/argocd/argocd/app.yaml)
- [Helm values](../../../../apps/argocd/argocd/values.yaml)
- [Raw manifests](../../../../apps/argocd/argocd/manifests)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Networking](../../architecture/networking.md)
- [Validation architecture](../../decisions/validation-architecture.md)
