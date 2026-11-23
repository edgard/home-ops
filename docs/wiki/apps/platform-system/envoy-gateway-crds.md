# Envoy Gateway CRDs

Purpose: install the standard Kubernetes Gateway API and Envoy Gateway's extension APIs.
Status: current. Reviewed against: `b898924ceaf8be0a1b00e20fed8f57369259f669`.

Foundation needs the HTTPRoute API before Helm can install Argo CD's server
route. It renders this app's chart pin and values, applies the definitions with
the Argo field manager and checks API discovery. GitOps takes ownership after
handoff. Subsequent foundation runs check the definitions reported by the Argo
Application and wait for discovery. On an unowned cluster, foundation checks
the existing standard bundle version and channel before applying any schemas.
The Envoy controller chart disables its bundled CRD installation.

The app has no running workload or PVC. Its CRDs store the API definitions used
by every routed application. Deleting a CRD also deletes its instances. Protect
the definitions and their safe-upgrades admission policy and binding during
ownership transfers. Review changes to the packaged Gateway API schemas with
each CRD chart update. Before a downgrade, compare live stored versions and
object fields against the target schemas and rehearse the downgrade and upgrade
on an isolated API server. Keep an off-node etcd snapshot for recovery.

## Sources

- [CRD chart pin](../../../../apps/platform-system/envoy-gateway-crds/app.yaml) and [channel selection](../../../../apps/platform-system/envoy-gateway-crds/values.yaml)
- [First-install ownership and version checks](../../../../ansible/roles/platform/tasks/install_gateway_crds.yml) and [foundation API discovery](../../../../ansible/roles/platform/tasks/gateway_api.yml)
- [Renovate policy](../../../../.renovaterc.json5)
- [Upstream CRD management](https://gateway-api.sigs.k8s.io/guides/crd-management/) explains storage-version compatibility and downgrade risks.

## Related pages

- [Envoy Gateway](envoy-gateway.md)
- [Argo CD](../argocd/argocd.md)
- [Talos bootstrap and recovery](../../architecture/talos-bootstrap.md)
