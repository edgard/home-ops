# Kubelet CSR approver

Purpose: approve scoped kubelet serving-certificate requests so metrics collection survives certificate renewal.
Status: current. Reviewed against: `15c898cf` and this revision.

## Dependencies and approval scope

Talos enables serving-certificate rotation in the
[control-plane patch](../../../../ansible/roles/talos/files/controlplane-patch.yaml).
The kubelet requests certificates from Kubernetes, this controller approves
eligible requests, and the Kubernetes signer issues the certificates.
Platform foundation installs this same release before its storage observer
reads pod logs, avoiding a fresh-bootstrap dependency on Argo CD. Argo CD
subsequently reconciles the same resources from the same tracked values.

The [values](../../../../apps/kube-system/kubelet-csr-approver/values.yaml)
restrict DNS SANs to the exact node hostname and IP SANs to the approver pod's
host IP as an IPv4 `/32`. This is a single-node IPv4 policy. Before adding
nodes or IPv6, redesign that policy rather than widening it implicitly.
DNS resolution is bypassed because the explicit hostname and IP constraints
provide the allowlist; hostname matching remains enabled. Non-node requests
and invalid requests are left pending rather than denied.

The service account can read CSRs and update approval, with signer approval
limited to `kubernetes.io/kubelet-serving`. It cannot approve API client
certificates and does not receive Talos API credentials. The small offline
credential-scope check protects this boundary. The
[upstream validation rules](https://github.com/postfinance/kubelet-csr-approver/blob/v1.2.16/README.md#which-verifications-do-we-put-in-place-)
explain the request checks; the configured allowlists remain essential.

## Data and recovery

The controller has no PVC or private CA key. Requests and issued certificates
live in Kubernetes; the kubelet retains its certificate on the node.
Keep the approver deployed for subsequent renewals. Restore it through Argo CD
after recovery, and inspect pending CSRs and its logs if issuance stalls.

## Networking and monitoring

Only the Kubernetes API and an internal health endpoint are needed. No routed
endpoint or metrics Service is exposed. VictoriaMetrics and metrics-server
validate kubelet certificates with their mounted Kubernetes cluster CA.
Verify issuance and both consumers after applying the Talos setting; a healthy
controller process alone does not prove certificate approval works.

## Sources

- [Application](../../../../apps/kube-system/kubelet-csr-approver/app.yaml)
- [Values and RBAC](../../../../apps/kube-system/kubelet-csr-approver/values.yaml)
- [Credential-scope check](../../../../validation/test_repository.py)
- [Foundation release inputs](../../../../ansible/roles/platform/defaults/main.yml) and [bootstrap order](../../../../ansible/roles/platform/tasks/bootstrap.yml)
- [Talos rotation procedure](https://docs.siderolabs.com/kubernetes-guides/monitoring-and-observability/deploy-metrics-server#option-2-rotate-kubelet-certificates)

## Related pages

- [Talos bootstrap](../../architecture/talos-bootstrap.md#kubelet-serving-certificates)
- [VictoriaMetrics](../platform-system/victoria-metrics.md)
- [metrics-server](metrics-server.md)
