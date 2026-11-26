# Networking and ingress

Purpose: connect the cluster's routes, local network, and external DNS sources.
Status: current. Reviewed against: `042a505f` and this revision.

Routed apps attach HTTPRoutes to the shared Envoy Gateway listener in
`platform-system`. Cloudflare DNS is managed in Terraform, while the cluster
also runs External DNS and a Tailscale router. LAN and Tailscale clients resolve application names privately.
[Cloudflare Tunnel](../apps/platform-system/cloudflared.md) publishes Karakeep
through Access. Atuin uses private DNS while its public route is suspended. OpenTofu controls public DNS separately for each app.

Multus supplies a LAN bridge for workloads needing direct LAN traffic, such as
Jellyfin discovery. Its network attachment and each workload's annotation are
separate sources; a routed HTTPS endpoint and a direct LAN listener can coexist.

The [Samba pod](../apps/selfhosted/samba.md) uses the node's reserved LAN
address and TCP port 445. Kubernetes forwards that port to the pod. The service
uses its own source restrictions, outside the HTTP Gateway and Tailscale routes.

## Find the node on the LAN

Talos sets the short hostname `homelab`. The LAN resolver owns its forward
and reverse records. To find the name for the reserved node address from a
LAN client, query the PTR record and check that the returned name resolves
back to that address.

```sh
node_name=$(dig +short -x "$TALOS_NODE")
echo "$node_name"
dig +short "$node_name" A
dig +search +short homelab A
```

Use the LAN name for the [SMB shares](../apps/selfhosted/samba.md#lan-access-and-recovery).
For API clients, use the configured Talos or Kubernetes endpoint. Connecting
through another DNS name also requires that name in the server certificate.

Inside Pods, CoreDNS answers Kubernetes Service names such as
`kubernetes.default.svc.cluster.local`, forwards `edgard.org` to
k8s-gateway for HTTPRoute discovery, and sends other queries upstream.
For routed applications, check resolution and HTTPS from a pod as well as a
LAN client. The proxy Service supplies the internal Gateway address. External DNS
publishes the Multus address to UniFi and Tailscale advertises a route to it.

## Sources

- [Talos hostname and bridge](../../../ansible/roles/talos/files/controlplane-patch.yaml)
- [CoreDNS forwarding](../../../apps/kube-system/coredns/values.yaml) and [k8s-gateway discovery](../../../apps/kube-system/k8s-gateway/values.yaml)
- [Gateway and proxy configuration](../../../apps/platform-system/envoy-gateway/manifests)
- [Multus network attachment](../../../apps/kube-system/multus/manifests/multus-lan-bridge.networkattachmentdefinition.yaml)
- [Cloudflare DNS module](../../../terraform/cloudflare/dns.tf)
- [Tailscale router values](../../../apps/platform-system/tailscale-router/values.yaml)
- [Jellyfin values](../../../apps/media/jellyfin/values.yaml)

## Related pages

- [GitOps delivery](gitops-delivery.md)
- [Uptime monitoring](uptime.md)
- [Jellyfin migration decision](../decisions/jellyfin-cutover.md)
