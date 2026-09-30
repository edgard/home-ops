# Tailscale router

Purpose: The Tailscale router advertises access paths into the local network.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

## Dependencies

It needs a node TUN device, service-account access to its state Secret, and ExternalSecret credentials.

## Data and recovery

No app-owned PVC is declared in these values. Check chart defaults and raw manifests before treating the workload as stateless. The host path mount (`dev-tun`) depends on the node.

## Networking and monitoring

No routed HTTP endpoint is declared in this app values file; inspect raw manifests and chart output for other exposure.

## Operational note

Its elevated network capability is purposeful; route advertisement changes affect remote access.

## Sources

- [App metadata](../../../../apps/platform-system/tailscale-router/app.yaml)
- [Helm values](../../../../apps/platform-system/tailscale-router/values.yaml)
- [Raw manifests](../../../../apps/platform-system/tailscale-router/manifests)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Networking](../../architecture/networking.md)
