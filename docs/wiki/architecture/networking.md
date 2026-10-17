# Networking and ingress

Purpose: connect the cluster's routes, local network, and external DNS sources.
Status: current. Reviewed against: `0347fad141d7dfe0692ab03b8636296f0921548a`.

Routed apps attach HTTPRoutes to the Istio Gateway API listener in
`platform-system`. Cloudflare DNS is managed in Terraform, while the cluster
also runs External DNS and a Tailscale router. The homelab is intended for
local and Tailscale access; a route or DNS record alone does not prove a service
is reachable from every client.

Multus supplies a LAN bridge for workloads needing direct LAN traffic, such as
Jellyfin discovery. Its network attachment and each workload's annotation are
separate sources; a routed HTTPS endpoint and a direct LAN listener can coexist.

Home Assistant owns a separate bridge/tuning attachment for its shared Matter
Server pod. It preserves the existing LAN identity and enables IPv6 router
advertisements and Thread route-information acceptance inside that pod. Other
consumers keep the shared attachment. Matter's management API remains on pod
loopback; IPv6 device traffic uses the direct LAN interface. See the
[Home Assistant page](../apps/home-automation/homeassistant.md) for setup and
acceptance. These pod settings do not enable IPv6 forwarding on the Talos host.

## Sources

- [Istio Gateway](../../../apps/platform-system/istio/manifests/istio-gateway.gateway.yaml)
- [Multus network attachment](../../../apps/kube-system/multus/manifests/multus-lan-bridge.networkattachmentdefinition.yaml)
- [Cloudflare DNS module](../../../terraform/cloudflare/dns.tf)
- [Tailscale router values](../../../apps/platform-system/tailscale-router/values.yaml)
- [Jellyfin values](../../../apps/media/jellyfin/values.yaml)
- [Home Assistant network attachment](../../../apps/home-automation/homeassistant/manifests/homeassistant-matter-lan.networkattachmentdefinition.yaml)

## Related pages

- [GitOps delivery](gitops-delivery.md)
- [Uptime monitoring](uptime.md)
- [Jellyfin migration decision](../decisions/jellyfin-cutover.md)
