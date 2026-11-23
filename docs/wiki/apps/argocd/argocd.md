# Argo CD

Purpose: Argo CD reconciles the applications generated from repository metadata.
Status: current. Reviewed against: `b898924ceaf8be0a1b00e20fed8f57369259f669`.

## Dependencies

Platform bootstrap installs Argo CD after its storage, networking, certificate,
and secret prerequisites. Its Helm chart creates the server HTTPRoute, so
foundation waits for the [Envoy Gateway CRDs](../platform-system/envoy-gateway-crds.md)
before installing that release.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless.

## Networking and monitoring

The [app values](../../../../apps/argocd/argocd/values.yaml) define the Gateway route and declare its Blackbox probe URL on the web Service.

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
