# VictoriaMetrics

Purpose: collect and store one year of metrics for Grafana.
Status: current. Reviewed against: `15c898cf` and this revision.

One process discovers application probes from labeled Services, scrapes the explicit infrastructure targets and serves the private query API. The appdata claim retains samples across pod replacements. Recover the data from the platform-system Restic snapshot after pool loss. Authenticate kubelet scrapes with the dedicated service account and validate its serving certificate against the Kubernetes cluster CA mounted with that account.

The query and ingestion API is reachable on the cluster network. The deletion
API requires a rotating projected token with its own audience, mounted only
in the VictoriaMetrics pod. Ordinary scrapes use a separate credential.

## Kubelet certificate trust

The [Talos patch](../../../../ansible/roles/talos/files/controlplane-patch.yaml)
enables serving-certificate rotation. The
[kubelet CSR approver](../kube-system/kubelet-csr-approver.md) validates requests
before Kubernetes signs them. The scrape trusts the mounted cluster CA and
checks the `homelab` server name; no per-restart CA pin is needed.

For `x509: certificate signed by unknown authority`, check the Talos rotation
setting, pending `kubernetes.io/kubelet-serving` CSRs and the approver's logs.
The default self-signed certificate is not trusted by this scrape. Follow the
[bootstrap runbook](../../architecture/talos-bootstrap.md#kubelet-serving-certificates)
to apply the rotation setting to an existing node. Do not disable verification.
Check `up{job="kubelet"} == 1` and fresh pod working-set memory after upgrades.

## Sources

- [Application](../../../../apps/platform-system/victoria-metrics/app.yaml)
- [Helm values](../../../../apps/platform-system/victoria-metrics/values.yaml)
- [Scrape trust and authentication](../../../../apps/platform-system/victoria-metrics/manifests/victoria-metrics-scrape.configmap.yaml)

## Related pages

- [Monitoring and cutover](../../architecture/uptime.md)
- [Kubelet CSR approver](../kube-system/kubelet-csr-approver.md)
