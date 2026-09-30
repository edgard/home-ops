# Networking and ingress

Purpose: connect the cluster's routes, local network, and external DNS sources.
Status: current. Reviewed against: `2b1488a25dc2af9e6c4d35c0960cba3306b6ec7b`.

Routed apps attach HTTPRoutes to the Istio Gateway API listener in
`platform-system`. Cloudflare DNS is managed in Terraform, while the cluster
also runs External DNS and a Tailscale router. The homelab is intended for
local and Tailscale access; a route or DNS record alone does not prove a service
is reachable from every client.

Multus supplies a LAN bridge for workloads needing direct LAN traffic, such as
Jellyfin discovery. Its network attachment and each workload's annotation are
separate sources; a routed HTTPS endpoint and a direct LAN listener can coexist.

## Sources

- [Istio Gateway](../../../apps/platform-system/istio/manifests/istio-gateway.gateway.yaml)
- [Multus network attachment](../../../apps/kube-system/multus/manifests/multus-lan-bridge.networkattachmentdefinition.yaml)
- [Cloudflare DNS module](../../../terraform/cloudflare/dns.tf)
- [Tailscale router values](../../../apps/platform-system/tailscale-router/values.yaml)
- [Jellyfin values](../../../apps/media/jellyfin/values.yaml)

## Related pages

- [GitOps delivery](gitops-delivery.md)
- [Uptime monitoring](uptime.md)
- [Jellyfin migration decision](../decisions/jellyfin-cutover.md)
