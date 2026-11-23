# Envoy Gateway

Purpose: serve the cluster's HTTPRoutes through the shared LAN gateway.
Status: current. Reviewed against: `b898924ceaf8be0a1b00e20fed8f57369259f669`.

The controller watches the Envoy GatewayClass and creates the proxy Deployment
and Service. The Gateway accepts routes from application namespaces. Its HTTPS
listeners use the Secret maintained by cert-manager. The chart's certgen hook
creates separate credentials for controller-to-proxy communication.

The proxy uses a Multus interface with a fixed IP and MAC. A single replica and
the Recreate strategy release that interface before a replacement acquires it.
Clients reach the pod's listener ports directly on the LAN, so the proxy binds
the same low ports as the Service. Tailscale permits the web ports. The two
read-only health endpoints are reachable on the trusted LAN. Proxy Prometheus
metrics are disabled. The gateway timeout policy permits long-running requests.

The app has no persistent volume. If the Gateway is replaced, wait for the old
pod to terminate before assigning its address to the new proxy. Compare the
HTTPRoute parent conditions and check an actual HTTPS request from both the LAN
and the cluster. A successful Kubernetes readiness probe only checks the pod.

## Sources

- [Controller chart](../../../../apps/platform-system/envoy-gateway/app.yaml) and [Helm values](../../../../apps/platform-system/envoy-gateway/values.yaml)
- [Gateway, timeout policy and proxy deployment settings](../../../../apps/platform-system/envoy-gateway/manifests)
- [Tailscale route and ACL](../../../../terraform/tailscale.tf)
- [Upstream proxy API](https://gateway.envoyproxy.io/docs/api/extension_types/#envoyproxykubernetesprovider) documents Service and listener port mapping.

## Related pages

- [Envoy Gateway CRDs](envoy-gateway-crds.md)
- [cert-manager](cert-manager.md)
- [Networking and ingress](../../architecture/networking.md)
